import random
import uuid
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict

from imposter.config import (
    GameConfig,
    GameOutcome,
    GamePhase,
    PlayerConfig,
    PlayerRole,
    SecretWord,
)
from imposter.engine.events import (
    BaseGameEvent,
    ClueGivenEvent,
    GameAbortedEvent,
    GameFinishedEvent,
    GameStartedEvent,
    GuessMadeEvent,
    OutcomeEvent,
    PhaseStartedEvent,
    PlayerErrorEvent,
    PublicSeat,
    PublicVote,
    ReflectionEvent,
    SecretWordSaidEvent,
    StatementMadeEvent,
    TurnStartedEvent,
    UsageEvent,
    VoteCastEvent,
    VotesRevealedEvent,
)
from imposter.engine.views import (
    GameReveal,
    GameRules,
    PlayerView,
    PublicClue,
    PublicGuess,
    PublicStatement,
    ScratchpadEntry,
    VoteResult,
)
from imposter.utils.names import seat_names
from imposter.utils.phases import (
    PARALLEL_PHASES,
    SEQUENTIAL_PHASES,
    TERMINAL_PHASES,
    PhaseTransitionReason,
    next_phase,
    transition_target,
)
from imposter.utils.tally import caught_seats, count_votes, decide_outcome
from imposter.utils.text import (
    clean_word,
    is_single_word,
    mentions_word,
    normalize_word,
    truncate_words,
)

ACTION_EVENT_TYPES = (
    ClueGivenEvent,
    StatementMadeEvent,
    VoteCastEvent,
    GuessMadeEvent,
    ReflectionEvent,
)
"""The events that complete the turn of a seat."""


class InvalidActionError(Exception):
    """Raised when an action is not allowed in the current state of a game."""


class Seat(BaseModel):
    """Who sits at a seat, fixed at setup.

    Attributes:
        seat: The 0-based seat number, which is also the turn order.
        name: The display name under the identity mode.
        role: The secret role.
        player: The config of the player at this seat.
    """

    model_config = ConfigDict(frozen=True)

    seat: int
    name: str
    role: PlayerRole
    player: PlayerConfig


class ActionRejection(BaseModel):
    """Why a clue or vote cannot be accepted.

    Attributes:
        reason: The reason, safe to show to the player who gave the clue or vote.
        retryable: Whether the player may try again. An imposter who happens to say the
            secret word is not told why, because that would reveal the word, and passes.
    """

    model_config = ConfigDict(frozen=True)

    reason: str
    retryable: bool = True


class Game:
    """One game of Imposter: its setup, its event log and the rules that change it.

    The event log is the only state that changes. Every query, such as the current
    phase, who still has to act or what a seat may see, is derived from it, so nothing
    can drift out of sync. Every event records the phase and round it happened in, so
    the current phase is the phase of the last event.

    The game is pure: it calls no models and does no I/O. A caller asks `pending_seats`
    who must act, calls `start_turn`, gives the player `view_for` its seat, and submits
    the answer with the method for the phase. Decisions that need a model, such as
    whether a guess is a synonym of the word, are made by the caller and passed in.

    Attributes:
        game_id: The id of the game.
        config: The options of the game.
        secret: The secret word, category and hint.
        seats: Who sits at each seat, in seat order.
    """

    def __init__(
        self,
        *,
        game_id: str,
        config: GameConfig,
        secret: SecretWord,
        seats: list[Seat],
        events: list[BaseGameEvent] | None = None,
    ) -> None:
        """Initialize a game from its parts, for example when importing an export.

        Use `create` to set up a new game with random seats and roles.

        Args:
            game_id: The id of the game.
            config: The options of the game.
            secret: The secret word, category and hint.
            seats: Who sits at each seat, in seat order.
            events: The events so far, empty for a game that has not started.
        """
        self.game_id = game_id
        self.config = config
        self.secret = secret
        self.seats = tuple(seats)
        self._events: list[BaseGameEvent] = list(events or [])

    @classmethod
    def create(
        cls, *, config: GameConfig, secret: SecretWord, game_id: str | None = None
    ) -> Self:
        """Set up a game: shuffle seats, pick imposters, name seats and start round 1.

        Seat order and roles come from `config.seed`, so a fixed seed gives
        the same setup.

        Args:
            config: The options of the game.
            secret: The secret word, category and hint.
            game_id: The id of the game, a random id when not given.

        Returns:
            The game, in the first clue round.

        Raises:
            ValueError: When the hint is missing while enabled, or is the secret word.
        """
        if config.imposter_hint and not secret.hint:
            message = "The imposter hint is enabled but the secret has no hint."
            raise ValueError(message)

        if secret.hint and normalize_word(secret.hint) == normalize_word(secret.word):
            message = "The imposter hint must differ from the secret word."
            raise ValueError(message)

        rng = random.Random(config.seed)
        players = list(config.players)
        rng.shuffle(players)
        imposters = set(rng.sample(range(len(players)), k=config.imposter_count))
        names = seat_names(mode=config.identity_mode, players=players)
        seats = [
            Seat(
                seat=seat,
                name=names[seat],
                role=PlayerRole.IMPOSTER if seat in imposters else PlayerRole.CIVILIAN,
                player=player,
            )
            for seat, player in enumerate(players)
        ]
        game = cls(
            game_id=game_id or uuid.uuid4().hex, config=config, secret=secret, seats=seats
        )
        game.emit(
            GameStartedEvent,
            phase=GamePhase.SETUP,
            round=None,
            identity_mode=config.identity_mode,
            seats=game.public_seats(),
            imposter_count=config.imposter_count,
            clue_rounds=config.clue_rounds,
            discussion_rounds=config.discussion_rounds,
            public_category=secret.category if config.public_category else None,
            word=secret.word,
            category=secret.category,
            hint=secret.hint if config.imposter_hint else None,
            seat_models=[seat.player.model_id for seat in game.seats],
            imposters=game.imposters,
        )
        game.advance()

        return game

    @property
    def events(self) -> tuple[BaseGameEvent, ...]:
        """All events so far, in order of `seq`."""
        return tuple(self._events)

    @property
    def phase(self) -> GamePhase:
        """The current phase, the phase of the last event."""
        return self._events[-1].phase

    @property
    def round(self) -> int | None:
        """The current round, for clue and discussion phases."""
        return self._events[-1].round

    @property
    def is_over(self) -> bool:
        """Whether the game is done or aborted."""
        return self.phase in TERMINAL_PHASES

    @property
    def is_sequential(self) -> bool:
        """Whether seats act one at a time in the current phase."""
        return self.phase in SEQUENTIAL_PHASES

    @property
    def imposters(self) -> list[int]:
        """The imposter seats, in seat order."""
        return [seat.seat for seat in self.seats if seat.role is PlayerRole.IMPOSTER]

    @property
    def phase_events(self) -> list[BaseGameEvent]:
        """The events since the current phase or round started."""
        starts = [
            index
            for index, event in enumerate(self._events)
            if isinstance(event, PhaseStartedEvent)
        ]

        return self._events[starts[-1] + 1 :] if starts else []

    @property
    def pending_seats(self) -> list[int]:
        """The seats that still have to act in the current phase, in turn order."""
        if self.phase not in SEQUENTIAL_PHASES | PARALLEL_PHASES:
            return []

        acting = (
            self.imposters
            if self.phase is GamePhase.GUESS
            else [seat.seat for seat in self.seats]
        )
        acted = {
            event.seat
            for event in self.phase_events
            if isinstance(event, ACTION_EVENT_TYPES)
        }

        return [seat for seat in acting if seat not in acted]

    @property
    def started_seats(self) -> set[int]:
        """The seats whose turn started in the current phase."""
        return {
            event.seat
            for event in self.phase_events
            if isinstance(event, TurnStartedEvent)
        }

    @property
    def votes_revealed(self) -> VotesRevealedEvent | None:
        """The revealed votes, or `None` before the resolution."""
        revealed = self.events_of_type(VotesRevealedEvent)

        return revealed[-1] if revealed else None

    @property
    def outcome(self) -> GameOutcome | None:
        """How the game ended, or `None` before it is decided."""
        outcomes = self.events_of_type(OutcomeEvent)

        return outcomes[-1].outcome if outcomes else None

    @property
    def tokens_used(self) -> int:
        """The input, output and thinking tokens of every turn so far, summed."""
        return sum(
            event.input_tokens + event.output_tokens + event.thinking_tokens
            for event in self.events_of_type(UsageEvent)
        )

    def events_of_type[EventT: BaseGameEvent](
        self, event_type: type[EventT]
    ) -> list[EventT]:
        """List the events of one type.

        Args:
            event_type: The event class.

        Returns:
            The events of that type, in order.
        """
        return [event for event in self._events if isinstance(event, event_type)]

    def public_seats(self) -> list[PublicSeat]:
        """List the seats as everyone at the table knows them.

        Returns:
            The seat number and display name of every seat, in seat order.
        """
        return [PublicSeat(seat=seat.seat, name=seat.name) for seat in self.seats]

    def seat_by_name(self, name: str) -> int | None:
        """Find a seat by its display name, ignoring case and surrounding whitespace.

        Args:
            name: The display name.

        Returns:
            The seat, or `None` when no seat has that name.
        """
        wanted = name.strip().casefold()

        return next(
            (seat.seat for seat in self.seats if seat.name.casefold() == wanted), None
        )

    def clue_rejection(self, *, seat: int, clue: str) -> ActionRejection | None:
        """Run the cheap code checks on a clue.

        Args:
            seat: The seat giving the clue.
            clue: The raw clue.

        Returns:
            Why the clue is rejected, or `None` when it passes the code checks. A clue
            that says the secret word is not rejected: submitting it ends the game.
        """
        if self.clue_says_word(clue):
            return None

        cleaned = clean_word(clue)

        if not is_single_word(cleaned):
            return ActionRejection(reason="the clue must be exactly one word")

        normalized = normalize_word(cleaned)
        given = {
            normalize_word(event.clue)
            for event in self.events_of_type(ClueGivenEvent)
            if event.clue
        }

        if normalized in given:
            return ActionRejection(reason=f'"{cleaned}" was already given as a clue')

        return None

    def clue_says_word(self, clue: str) -> bool:
        """Check whether a clue says the secret word: is it, or contains it.

        Args:
            clue: The raw clue.

        Returns:
            `True` when the normalised clue contains the normalised secret word.
        """
        return normalize_word(self.secret.word) in normalize_word(clue)

    def statement_says_word(self, statement: str) -> bool:
        """Check whether a statement says the secret word as a whole word.

        Args:
            statement: The statement.

        Returns:
            `True` when the statement contains the word or a simple plural of it.
        """
        return mentions_word(text=statement, word=self.secret.word)

    def vote_rejection(self, *, voter: int, vote_for: str) -> ActionRejection | None:
        """Check that a vote names another player.

        Args:
            voter: The voting seat.
            vote_for: The display name the voter voted for.

        Returns:
            Why the vote is invalid, or `None` when it is valid.
        """
        target = self.seat_by_name(vote_for)

        if target is None:
            names = ", ".join(seat.name for seat in self.seats if seat.seat != voter)
            return ActionRejection(
                reason=f'"{vote_for}" is not a player; vote for one of: {names}'
            )

        if target == voter:
            return ActionRejection(reason="you cannot vote for yourself")

        return None

    def guess_is_exact(self, guess: str) -> bool:
        """Check whether a guess matches the secret word after normalisation.

        Args:
            guess: The guess.

        Returns:
            `True` for an exact match after normalisation.
        """
        normalized = normalize_word(guess)

        return bool(normalized) and normalized == normalize_word(self.secret.word)

    def start_turn(self, seat: int) -> None:
        """Start the turn of a seat, which must happen before it submits an action.

        In sequential phases only the first pending seat may start, in parallel phases
        every pending seat may start.

        Args:
            seat: The seat whose turn starts.

        Raises:
            InvalidActionError: When the seat may not start a turn now.
        """
        pending = self.pending_seats

        if seat not in pending or seat in self.started_seats:
            message = f"Seat {seat} has no turn to start in phase {self.phase}."
            raise InvalidActionError(message)

        if self.is_sequential and seat != pending[0]:
            message = f"It is the turn of seat {pending[0]}, not seat {seat}."
            raise InvalidActionError(message)

        self.emit(TurnStartedEvent, seat=seat)

    def submit_clue(
        self,
        *,
        seat: int,
        clue: str | None,
        private_reasoning: str,
        rejection_reason: str | None = None,
    ) -> None:
        """Record the clue of a seat for the current round.

        A clue that says the secret word ends the game (`end_by_secret_word`).

        Args:
            seat: The seat.
            clue: The clue, or `None` to pass. It must pass `clue_rejection`.
            private_reasoning: The reasoning of the seat, truncated to the cap.
            rejection_reason: Why an earlier attempt was rejected, when passing after an
                invalid clue.

        Raises:
            InvalidActionError: When it is not the seat's turn or the clue is invalid.
        """
        self.check_turn(seat=seat, phase=GamePhase.CLUE)

        if clue is not None and self.clue_says_word(clue):
            self.end_by_secret_word(
                seat=seat, text=clue, private_reasoning=private_reasoning
            )
            return

        if clue is not None:
            rejection = self.clue_rejection(seat=seat, clue=clue)

            if rejection is not None:
                message = f"Invalid clue from seat {seat}: {rejection.reason}."
                raise InvalidActionError(message)

            clue = clean_word(clue)

        reasoning, reasoning_truncated = self.truncate_reasoning(private_reasoning)
        self.emit(
            ClueGivenEvent,
            seat=seat,
            clue=clue,
            rejection_reason=rejection_reason,
            private_reasoning=reasoning,
            reasoning_truncated=reasoning_truncated,
        )
        self.finish_turn()

    def submit_statement(
        self, *, seat: int, statement: str, private_reasoning: str
    ) -> None:
        """Record the statement of a seat for the current discussion round.

        The statement is truncated to the cap. A statement that says the secret word ends
        the game (`end_by_secret_word`).

        Args:
            seat: The seat.
            statement: The statement, possibly empty.
            private_reasoning: The reasoning of the seat, truncated to the cap.

        Raises:
            InvalidActionError: When it is not the seat's turn.
        """
        self.check_turn(seat=seat, phase=GamePhase.DISCUSSION)
        statement, truncated = truncate_words(
            statement, cap=self.config.statement_word_cap
        )

        if self.statement_says_word(statement):
            self.end_by_secret_word(
                seat=seat, text=statement, private_reasoning=private_reasoning
            )
            return

        reasoning, reasoning_truncated = self.truncate_reasoning(private_reasoning)
        self.emit(
            StatementMadeEvent,
            seat=seat,
            statement=statement,
            truncated=truncated,
            private_reasoning=reasoning,
            reasoning_truncated=reasoning_truncated,
        )
        self.finish_turn()

    def submit_vote(
        self, *, voter: int, vote_for: str | None, private_reasoning: str
    ) -> None:
        """Record the secret vote of a seat. The last vote triggers the resolution.

        Args:
            voter: The voting seat.
            vote_for: The display name of another player, or `None` to abstain.
            private_reasoning: The reasoning of the seat, truncated to the cap.

        Raises:
            InvalidActionError: When it is not the seat's turn or the vote is invalid.
        """
        self.check_turn(seat=voter, phase=GamePhase.VOTE)
        target = None

        if vote_for is not None:
            rejection = self.vote_rejection(voter=voter, vote_for=vote_for)

            if rejection is not None:
                message = f"Invalid vote from seat {voter}: {rejection.reason}."
                raise InvalidActionError(message)

            target = self.seat_by_name(vote_for)

        reasoning, reasoning_truncated = self.truncate_reasoning(private_reasoning)
        self.emit(
            VoteCastEvent,
            seat=voter,
            target=target,
            private_reasoning=reasoning,
            reasoning_truncated=reasoning_truncated,
        )
        self.finish_turn()

    def submit_guess(
        self,
        *,
        seat: int,
        guess: str,
        private_reasoning: str,
        judge_verdict: bool | None = None,
    ) -> None:
        """Record and judge the guess of an imposter.

        An exact match after normalisation is correct. Otherwise the verdict of the judge
        decides, when the caller consulted one. The game never calls the judge itself.

        Args:
            seat: The imposter seat.
            guess: The guess, empty when the imposter gave none.
            private_reasoning: The reasoning of the seat, truncated to the cap.
            judge_verdict: Whether the judge considers the guess the same word, or `None`
                when no judge was consulted.

        Raises:
            InvalidActionError: When it is not the seat's turn.
        """
        self.check_turn(seat=seat, phase=GamePhase.GUESS)
        guess = clean_word(guess)
        judged_by: Literal["exact", "judge", "none"] = "none"
        correct = False

        if self.guess_is_exact(guess):
            judged_by, correct = "exact", True
        elif guess and judge_verdict is not None:
            judged_by, correct = "judge", judge_verdict

        reasoning, reasoning_truncated = self.truncate_reasoning(private_reasoning)
        self.emit(
            GuessMadeEvent,
            seat=seat,
            guess=guess,
            correct=correct,
            judged_by=judged_by,
            private_reasoning=reasoning,
            reasoning_truncated=reasoning_truncated,
        )
        self.finish_turn()

    def submit_reflection(self, *, seat: int, reflection: str) -> None:
        """Record the debrief reflection of a seat. The last one finishes the game.

        Args:
            seat: The seat.
            reflection: The reflection, possibly empty.

        Raises:
            InvalidActionError: When it is not the seat's turn.
        """
        self.check_turn(seat=seat, phase=GamePhase.DEBRIEF)
        self.emit(ReflectionEvent, seat=seat, reflection=reflection.strip())
        self.finish_turn()

    def end_by_secret_word(self, *, seat: int, text: str, private_reasoning: str) -> None:
        """End the game because a seat said the secret word, which loses it for its side.

        The remaining clue, discussion, vote and guess phases are skipped: the outcome is
        decided at once and the debrief follows.

        Args:
            seat: The seat that said the word.
            text: The clue or statement that said it.
            private_reasoning: The reasoning of the seat, truncated to the cap.
        """
        reasoning, reasoning_truncated = self.truncate_reasoning(private_reasoning)
        target = transition_target(
            source=self.phase, reason=PhaseTransitionReason.SECRET_WORD_SAID
        )
        self.emit(
            SecretWordSaidEvent,
            seat=seat,
            text=text,
            private_reasoning=reasoning,
            reasoning_truncated=reasoning_truncated,
        )
        self.emit(PhaseStartedEvent, phase=target, round=None)
        self.reveal_outcome()
        self.advance()

    def record_usage(
        self,
        *,
        seat: int,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        thinking_tokens: int = 0,
    ) -> None:
        """Record the tokens used by a turn and abort when the budget is exceeded.

        Usage is recorded in any phase, also after the game is over, because the tokens
        were spent either way.

        Args:
            seat: The seat whose turn used the tokens.
            model_id: The model that used the tokens.
            input_tokens: The prompt tokens.
            output_tokens: The completion tokens.
            thinking_tokens: The thinking tokens.
        """
        total = self.tokens_used + input_tokens + output_tokens + thinking_tokens
        self.emit(
            UsageEvent,
            seat=seat,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            total_tokens=total,
        )

        if not self.is_over and total > self.config.token_budget:
            self.abort(f"token budget of {self.config.token_budget} exceeded")

    def record_player_error(self, *, seat: int, message: str) -> None:
        """Record that a player failed to produce a valid action.

        Args:
            seat: The seat.
            message: What went wrong.
        """
        self.emit(PlayerErrorEvent, seat=seat, message=message)

    def abort(self, reason: str) -> None:
        """Stop the game before its end.

        Args:
            reason: Why the game is aborted.

        Raises:
            InvalidActionError: When the game is already over.
        """
        if self.is_over:
            message = f"The game is already over in phase {self.phase}."
            raise InvalidActionError(message)

        self.emit(GameAbortedEvent, phase=GamePhase.ABORTED, round=None, reason=reason)

    def view_for(self, seat: int) -> PlayerView:
        """Build what one seat may see, as listed in `game-rules.md` §Views.

        Civilians see the word, imposters see the hint when enabled, and everyone sees
        the public transcript and only their own scratchpad. Votes appear only after
        they are revealed, and the word, roles and guesses only once the outcome is
        decided.

        Args:
            seat: The seat.

        Returns:
            The view of the seat.
        """
        config = self.config
        is_imposter = self.seats[seat].role is PlayerRole.IMPOSTER
        reveal = self.reveal()
        revealed_votes = self.votes_revealed

        return PlayerView(
            game_id=self.game_id,
            phase=self.phase,
            round=self.round,
            rules=GameRules(
                player_count=len(self.seats),
                imposter_count=config.imposter_count,
                clue_rounds=config.clue_rounds,
                discussion_rounds=config.discussion_rounds,
                statement_word_cap=config.statement_word_cap,
                reasoning_word_cap=config.reasoning_word_cap,
            ),
            seat=seat,
            name=self.seats[seat].name,
            role=self.seats[seat].role,
            word=self.secret.word if not is_imposter or reveal else None,
            hint=self.secret.hint if is_imposter and config.imposter_hint else None,
            category=self.secret.category if config.public_category or reveal else None,
            players=self.public_seats(),
            clues=[
                PublicClue(round=event.round, seat=event.seat, clue=event.clue)
                for event in self.events_of_type(ClueGivenEvent)
            ],
            statements=[
                PublicStatement(
                    round=event.round,
                    seat=event.seat,
                    statement=event.statement,
                    truncated=event.truncated,
                )
                for event in self.events_of_type(StatementMadeEvent)
            ],
            vote_result=(
                VoteResult(votes=revealed_votes.votes, caught=revealed_votes.caught)
                if revealed_votes
                else None
            ),
            reveal=reveal,
            scratchpad=self.scratchpad_for(seat),
        )

    def scratchpad_for(self, seat: int) -> list[ScratchpadEntry]:
        """List the earlier turns of a seat with its private reasoning.

        Only the seat's own clues, statements, votes and guesses are remembered. A vote
        is remembered only once the votes are revealed.

        Args:
            seat: The seat.

        Returns:
            The entries, in the order the turns were taken.
        """
        entries = []

        for event in self._events:
            match event:
                case ClueGivenEvent(seat=owner, clue=clue) if owner == seat:
                    action = f'gave the clue "{clue}"' if clue else "passed"
                case StatementMadeEvent(seat=owner, statement=statement) if owner == seat:
                    action = f'said "{statement}"'
                case VoteCastEvent(seat=owner, target=None) if owner == seat:
                    action = "abstained"
                case VoteCastEvent(seat=owner, target=int(target)) if owner == seat:
                    action = f"voted for {self.seats[target].name}"
                case GuessMadeEvent(seat=owner, guess=guess) if owner == seat:
                    action = f'guessed "{guess}"'
                case _:
                    continue

            if isinstance(event, VoteCastEvent) and self.votes_revealed is None:
                continue

            entries.append(
                ScratchpadEntry(
                    phase=event.phase,
                    round=event.round,
                    action=action,
                    private_reasoning=event.private_reasoning,
                )
            )

        return entries

    def reveal(self) -> GameReveal | None:
        """Build the reveal for the debrief once the outcome is decided.

        Returns:
            The word, roles, guesses and outcome, or `None` before the outcome.
        """
        outcomes = self.events_of_type(OutcomeEvent)

        if not outcomes:
            return None

        return GameReveal(
            word=self.secret.word,
            category=self.secret.category,
            imposters=self.imposters,
            guesses=[
                PublicGuess(seat=event.seat, guess=event.guess, correct=event.correct)
                for event in self.events_of_type(GuessMadeEvent)
            ],
            outcome=outcomes[-1].outcome,
            word_said_by=outcomes[-1].word_said_by,
        )

    def emit(self, event_type: type[BaseGameEvent], **fields: Any) -> None:
        """Append an event to the log, stamped with the current phase and round.

        Args:
            event_type: The event class.
            **fields: The fields of the event. `phase` and `round` override the current
                ones, for events that move the game to another phase.
        """
        stamp: dict[str, Any] = (
            {"phase": self.phase, "round": self.round} if self._events else {}
        )
        self._events.append(
            event_type(game_id=self.game_id, seq=len(self._events), **{**stamp, **fields})
        )

    def check_turn(self, *, seat: int, phase: GamePhase) -> None:
        """Check that a seat has a started turn in the given phase.

        Args:
            seat: The seat about to act.
            phase: The phase the action belongs to.

        Raises:
            InvalidActionError: When the game is in another phase or the seat has no
                started turn.
        """
        if self.phase is not phase:
            message = f"Cannot act in phase {phase} while the game is in {self.phase}."
            raise InvalidActionError(message)

        if seat not in self.started_seats or seat not in self.pending_seats:
            message = f"Seat {seat} has no started turn in phase {phase}."
            raise InvalidActionError(message)

    def truncate_reasoning(self, reasoning: str) -> tuple[str, bool]:
        """Cut private reasoning down to the cap of the game.

        Args:
            reasoning: The reasoning.

        Returns:
            The possibly shortened reasoning and whether words were removed.
        """
        return truncate_words(reasoning, cap=self.config.reasoning_word_cap)

    def finish_turn(self) -> None:
        """Advance to the next phase once every pending seat has acted."""
        if not self.pending_seats:
            self.advance()

    def advance(self) -> None:
        """Move to the next phase, playing the phases that need no player actions."""
        while True:
            phase, round_ = next_phase(
                phase=self.phase, round_=self.round, config=self.config
            )

            if phase is GamePhase.DONE:
                self.emit(
                    GameFinishedEvent, phase=phase, round=None, outcome=self.outcome
                )
                return

            self.emit(PhaseStartedEvent, phase=phase, round=round_)

            match phase:
                case GamePhase.RESOLUTION:
                    self.reveal_votes()
                case GamePhase.OUTCOME:
                    self.reveal_outcome()
                case _:
                    return

    def reveal_votes(self) -> None:
        """Reveal and tally the votes and decide who is caught."""
        targets = {
            event.seat: event.target for event in self.events_of_type(VoteCastEvent)
        }
        counts = count_votes(targets.values())
        seats = range(len(self.seats))
        self.emit(
            VotesRevealedEvent,
            votes=[PublicVote(voter=voter, target=targets.get(voter)) for voter in seats],
            counts=[counts[seat] for seat in seats],
            caught=caught_seats(counts=counts, catch_count=self.config.imposter_count),
        )

    def reveal_outcome(self) -> None:
        """Decide the winner and reveal the word and the imposters."""
        revealed = self.votes_revealed
        caught = revealed.caught if revealed else []
        said = self.events_of_type(SecretWordSaidEvent)
        word_said_by = said[0].seat if said else None

        if word_said_by is None:
            outcome = decide_outcome(
                imposters=self.imposters,
                caught=caught,
                correct_guessers=[
                    event.seat
                    for event in self.events_of_type(GuessMadeEvent)
                    if event.correct
                ],
            )
        elif self.seats[word_said_by].role is PlayerRole.IMPOSTER:
            outcome = GameOutcome.IMPOSTER_SAID_WORD
        else:
            outcome = GameOutcome.CIVILIAN_SAID_WORD

        self.emit(
            OutcomeEvent,
            outcome=outcome,
            word=self.secret.word,
            imposters=self.imposters,
            caught=caught,
            word_said_by=word_said_by,
        )
