import random
import uuid
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict

from imposter.engine.config import (
    GameConfig,
    GameOutcome,
    GamePhase,
    PlayerConfig,
    PlayerRole,
    SecretWord,
)
from imposter.engine.errors import GameSetupError, InvalidActionError
from imposter.engine.events import (
    ClueGivenEvent,
    GameAbortedEvent,
    GameEventBase,
    GameFinishedEvent,
    GameStartedEvent,
    GuessJudgedEvent,
    GuessMadeEvent,
    OutcomeEvent,
    PhaseStartedEvent,
    PlayerErrorEvent,
    PublicSeat,
    PublicVote,
    ReflectionEvent,
    RoleAssignedEvent,
    StatementMadeEvent,
    TurnStartedEvent,
    UsageEvent,
    VoteCastEvent,
    VotesRevealedEvent,
)
from imposter.engine.phases import PhaseStep
from imposter.engine.rules import (
    clean_word,
    is_single_word,
    normalize_word,
    redact_word,
    truncate_words,
)
from imposter.engine.tally import caught_seats, count_votes
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


class SeatAssignment(BaseModel):
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
        reason: The reason, safe to show to the player who gave the clue.
        retryable: Whether the player may try again. An imposter who happens to say the
            secret word is not told why, because that would reveal the word, and passes.
    """

    model_config = ConfigDict(frozen=True)

    reason: str
    retryable: bool = True


class GameState:
    """The state machine of one game: phases, actions, events and per-seat views.

    The state is pure: it calls no models and does no I/O. A driver asks
    `pending_seats` who must act, calls `start_turn`, builds `view_for` the seat, gets a
    response from the player and submits it with the method for the phase. Every change
    appends events to `events`, the single source of truth for the UI and export.
    Decisions that need a model, such as whether a guess is a synonym of the word, are
    made by the caller and passed in.

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
        seats: list[SeatAssignment],
    ) -> None:
        """Initialize a game in the setup phase without emitting events.

        Use `create` to set up a game with random seats and roles.

        Args:
            game_id: The id of the game.
            config: The options of the game.
            secret: The secret word, category and hint.
            seats: Who sits at each seat, in seat order.
        """
        self.game_id = game_id
        self.config = config
        self.secret = secret
        self.seats = tuple(seats)
        self._step = PhaseStep(phase=GamePhase.SETUP)
        self._events: list[GameEventBase] = []
        self._pending: list[int] = []
        self._started: set[int] = set()
        self._clues: list[PublicClue] = []
        self._statements: list[PublicStatement] = []
        self._votes: dict[int, int | None] = {}
        self._vote_result: VoteResult | None = None
        self._guesses: dict[int, PublicGuess] = {}
        self._reflections: dict[int, str] = {}
        self._scratchpads: dict[int, list[ScratchpadEntry]] = {
            seat.seat: [] for seat in seats
        }
        self._outcome: GameOutcome | None = None
        self._tokens_used = 0

    @classmethod
    def create(
        cls, *, config: GameConfig, secret: SecretWord, game_id: str | None = None
    ) -> Self:
        """Set up a game: shuffle seats, pick imposters, name seats and start round 1.

        Seat order, roles and neutral names come from `config.seed`, so a fixed seed gives
        the same setup.

        Args:
            config: The options of the game.
            secret: The secret word, category and hint.
            game_id: The id of the game, a random id when not given.

        Returns:
            The game, in the first clue round.

        Raises:
            GameSetupError: When the hint is missing while enabled, or reveals the word.
        """
        if config.imposter_hint and not secret.hint:
            message = "the imposter hint is enabled but the secret has no hint"
            raise GameSetupError(message)

        if secret.hint and normalize_word(secret.hint) == normalize_word(secret.word):
            message = "the imposter hint must differ from the secret word"
            raise GameSetupError(message)

        rng = random.Random(config.seed)
        players = list(config.players)
        rng.shuffle(players)
        imposters = set(rng.sample(range(len(players)), k=config.imposter_count))
        names = config.identity_mode.seat_names(players=players, rng=rng)
        seats = [
            SeatAssignment(
                seat=seat,
                name=names[seat],
                role=PlayerRole.IMPOSTER if seat in imposters else PlayerRole.CIVILIAN,
                player=player,
            )
            for seat, player in enumerate(players)
        ]
        state = cls(
            game_id=game_id or uuid.uuid4().hex, config=config, secret=secret, seats=seats
        )
        state.start()

        return state

    @property
    def phase(self) -> GamePhase:
        """The current phase."""
        return self._step.phase

    @property
    def round(self) -> int | None:
        """The current round, for clue and discussion phases."""
        return self._step.round

    @property
    def events(self) -> tuple[GameEventBase, ...]:
        """All events so far, in order of `seq`."""
        return tuple(self._events)

    @property
    def is_over(self) -> bool:
        """Whether the game is done or aborted."""
        return self._step.is_terminal

    @property
    def is_sequential(self) -> bool:
        """Whether seats act one at a time in the current phase."""
        return self._step.is_sequential

    @property
    def pending_seats(self) -> list[int]:
        """The seats that still have to act in the current phase, in turn order."""
        return list(self._pending)

    @property
    def imposters(self) -> list[int]:
        """The imposter seats."""
        return [seat.seat for seat in self.seats if seat.role is PlayerRole.IMPOSTER]

    @property
    def outcome(self) -> GameOutcome | None:
        """How the game ended, once decided."""
        return self._outcome

    @property
    def tokens_used(self) -> int:
        """The tokens used by all turns so far."""
        return self._tokens_used

    def start(self) -> None:
        """Emit the setup events and move to the first clue round.

        Raises:
            InvalidActionError: When the game has already started.
        """
        if self._step.phase is not GamePhase.SETUP or self._events:
            message = "the game has already started"
            raise InvalidActionError(message)

        self.emit(
            GameStartedEvent,
            identity_mode=self.config.identity_mode,
            seats=self.public_seats(),
            imposter_count=self.config.imposter_count,
            clue_rounds=self.config.clue_rounds,
            discussion_rounds=self.config.discussion_rounds,
            public_category=self.secret.category if self.config.public_category else None,
            word=self.secret.word,
            category=self.secret.category,
            hint=self.secret.hint if self.config.imposter_hint else None,
            seat_models=[seat.player.model_id for seat in self.seats],
        )

        for seat in self.seats:
            self.emit(RoleAssignedEvent, seat=seat.seat, role=seat.role)

        self._advance()

    def public_seats(self) -> list[PublicSeat]:
        """List the seats as everyone at the table knows them.

        Returns:
            The seat number and display name of every seat, in seat order.
        """
        return [PublicSeat(seat=seat.seat, name=seat.name) for seat in self.seats]

    def seat_for_name(self, name: str) -> int | None:
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

    def start_turn(self, seat: int) -> None:
        """Start the turn of a seat, which must happen before it submits an action.

        In sequential phases only the first pending seat may start; in parallel phases
        every pending seat may start.

        Args:
            seat: The seat whose turn starts.

        Raises:
            InvalidActionError: When the seat may not start a turn now.
        """
        if seat not in self._pending or seat in self._started:
            message = f"seat {seat} has no turn to start in phase {self.phase}"
            raise InvalidActionError(message)

        if self.is_sequential and seat != self._pending[0]:
            message = f"it is the turn of seat {self._pending[0]}, not seat {seat}"
            raise InvalidActionError(message)

        self._started.add(seat)
        self.emit(TurnStartedEvent, seat=seat)

    def clue_rejection(self, *, seat: int, clue: str) -> ActionRejection | None:
        """Run the cheap code checks on a clue.

        Args:
            seat: The seat giving the clue.
            clue: The raw clue.

        Returns:
            Why the clue is rejected, or `None` when it passes the code checks.
        """
        cleaned = clean_word(clue)

        if not is_single_word(cleaned):
            return ActionRejection(reason="the clue must be exactly one word")

        normalized = normalize_word(cleaned)
        word = normalize_word(self.secret.word)

        if word in normalized:
            if self.seats[seat].role is PlayerRole.IMPOSTER:
                return ActionRejection(reason="the clue is not allowed", retryable=False)

            return ActionRejection(
                reason="the clue must not be or contain the secret word"
            )

        given = {normalize_word(entry.clue) for entry in self._clues if entry.clue}

        if normalized in given:
            return ActionRejection(reason=f'"{cleaned}" was already given as a clue')

        return None

    def submit_clue(
        self,
        *,
        seat: int,
        clue: str | None,
        private_reasoning: str,
        rejection_reason: str | None = None,
    ) -> None:
        """Record the clue of a seat for the current round.

        Args:
            seat: The seat.
            clue: The clue, or `None` to pass. It must pass `clue_rejection`.
            private_reasoning: The reasoning of the seat, truncated to the cap.
            rejection_reason: Why an earlier attempt was rejected, when passing after an
                invalid clue.

        Raises:
            InvalidActionError: When it is not the seat's turn or the clue is invalid.
        """
        self._require_turn(seat=seat, phase=GamePhase.CLUE)

        if clue is not None:
            rejection = self.clue_rejection(seat=seat, clue=clue)

            if rejection is not None:
                message = f"invalid clue from seat {seat}: {rejection.reason}"
                raise InvalidActionError(message)

            clue = clean_word(clue)

        round_ = self._current_round()
        reasoning, reasoning_truncated = self._truncate_reasoning(private_reasoning)
        self._clues.append(PublicClue(round=round_, seat=seat, clue=clue))
        self._remember(
            seat=seat,
            action=f'gave the clue "{clue}"' if clue else "passed",
            reasoning=reasoning,
        )
        self.emit(
            ClueGivenEvent,
            seat=seat,
            clue=clue,
            rejection_reason=rejection_reason,
            private_reasoning=reasoning,
            reasoning_truncated=reasoning_truncated,
        )
        self._complete_turn(seat)

    def submit_statement(
        self, *, seat: int, statement: str, private_reasoning: str
    ) -> None:
        """Record the statement of a seat for the current discussion round.

        The statement is truncated to the cap and the secret word is redacted from it.

        Args:
            seat: The seat.
            statement: The statement, possibly empty.
            private_reasoning: The reasoning of the seat, truncated to the cap.

        Raises:
            InvalidActionError: When it is not the seat's turn.
        """
        self._require_turn(seat=seat, phase=GamePhase.DISCUSSION)
        statement, truncated = truncate_words(
            statement, cap=self.config.statement_word_cap
        )
        statement = redact_word(text=statement, word=self.secret.word)
        reasoning, reasoning_truncated = self._truncate_reasoning(private_reasoning)
        self._statements.append(
            PublicStatement(
                round=self._current_round(),
                seat=seat,
                statement=statement,
                truncated=truncated,
            )
        )
        self._remember(seat=seat, action=f'said "{statement}"', reasoning=reasoning)
        self.emit(
            StatementMadeEvent,
            seat=seat,
            statement=statement,
            truncated=truncated,
            private_reasoning=reasoning,
            reasoning_truncated=reasoning_truncated,
        )
        self._complete_turn(seat)

    def vote_rejection(self, *, voter: int, vote_for: str) -> ActionRejection | None:
        """Check that a vote names another player.

        Args:
            voter: The voting seat.
            vote_for: The display name the voter voted for.

        Returns:
            Why the vote is invalid, or `None` when it is valid.
        """
        target = self.seat_for_name(vote_for)

        if target is None:
            names = ", ".join(seat.name for seat in self.seats if seat.seat != voter)
            return ActionRejection(
                reason=f'"{vote_for}" is not a player; vote for one of: {names}'
            )

        if target == voter:
            return ActionRejection(reason="you cannot vote for yourself")

        return None

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
        self._require_turn(seat=voter, phase=GamePhase.VOTE)
        target = None

        if vote_for is not None:
            rejection = self.vote_rejection(voter=voter, vote_for=vote_for)

            if rejection is not None:
                message = f"invalid vote from seat {voter}: {rejection.reason}"
                raise InvalidActionError(message)

            target = self.seat_for_name(vote_for)

        reasoning, reasoning_truncated = self._truncate_reasoning(private_reasoning)
        self._votes[voter] = target
        action = "abstained" if target is None else f"voted for {self.seats[target].name}"
        self._remember(seat=voter, action=action, reasoning=reasoning)
        self.emit(
            VoteCastEvent,
            seat=voter,
            target=target,
            private_reasoning=reasoning,
            reasoning_truncated=reasoning_truncated,
        )
        self._complete_turn(voter)

    def guess_is_exact(self, guess: str) -> bool:
        """Check whether a guess matches the secret word after normalisation.

        Args:
            guess: The guess.

        Returns:
            `True` for an exact match after normalisation.
        """
        normalized = normalize_word(guess)

        return bool(normalized) and normalized == normalize_word(self.secret.word)

    def submit_guess(
        self,
        *,
        seat: int,
        guess: str,
        private_reasoning: str,
        judge_verdict: bool | None = None,
    ) -> None:
        """Record and judge the guess of an imposter.

        An exact match after normalisation is correct. Otherwise the verdict of the
        injected judge decides, when the caller consulted one.

        Args:
            seat: The imposter seat.
            guess: The guess, empty when the imposter gave none.
            private_reasoning: The reasoning of the seat, truncated to the cap.
            judge_verdict: Whether the judge considers the guess the same word, or
                `None` when no judge was consulted.

        Raises:
            InvalidActionError: When it is not the seat's turn.
        """
        self._require_turn(seat=seat, phase=GamePhase.GUESS)
        guess = clean_word(guess)
        method: Literal["exact", "judge", "none"] = "none"
        correct = False

        if self.guess_is_exact(guess):
            method, correct = "exact", True
        elif guess and judge_verdict is not None:
            method, correct = "judge", judge_verdict

        reasoning, reasoning_truncated = self._truncate_reasoning(private_reasoning)
        self._guesses[seat] = PublicGuess(seat=seat, guess=guess, correct=correct)
        self._remember(seat=seat, action=f'guessed "{guess}"', reasoning=reasoning)
        self.emit(
            GuessMadeEvent,
            seat=seat,
            guess=guess,
            private_reasoning=reasoning,
            reasoning_truncated=reasoning_truncated,
        )
        self.emit(GuessJudgedEvent, seat=seat, correct=correct, method=method)
        self._complete_turn(seat)

    def submit_reflection(self, *, seat: int, reflection: str) -> None:
        """Record the debrief reflection of a seat. The last one finishes the game.

        Args:
            seat: The seat.
            reflection: The reflection, possibly empty.

        Raises:
            InvalidActionError: When it is not the seat's turn.
        """
        self._require_turn(seat=seat, phase=GamePhase.DEBRIEF)
        self._reflections[seat] = reflection.strip()
        self.emit(ReflectionEvent, seat=seat, reflection=reflection.strip())
        self._complete_turn(seat)

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
        self._tokens_used += input_tokens + output_tokens + thinking_tokens
        self.emit(
            UsageEvent,
            seat=seat,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            total_tokens=self._tokens_used,
        )

        if not self.is_over and self._tokens_used > self.config.token_budget:
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
            message = f"the game is already over in phase {self.phase}"
            raise InvalidActionError(message)

        self._step = PhaseStep(phase=GamePhase.ABORTED)
        self._pending.clear()
        self._started.clear()
        self.emit(GameAbortedEvent, reason=reason)

    def view_for(self, seat: int) -> PlayerView:
        """Build what one seat may see, as listed in `game-rules.md` §Views.

        Civilians see the word, imposters see the hint when enabled, and everyone sees
        the public transcript and only their own scratchpad. Votes appear only after
        they are revealed; the word, roles and guesses only once the outcome is decided.

        Args:
            seat: The seat.

        Returns:
            The view of the seat.
        """
        assignment = self.seats[seat]
        is_imposter = assignment.role is PlayerRole.IMPOSTER
        reveal = self._reveal()
        public_category = self.config.public_category or reveal is not None
        scratchpad = [
            entry
            for entry in self._scratchpads[seat]
            if entry.phase is not GamePhase.VOTE or self._vote_result is not None
        ]

        return PlayerView(
            game_id=self.game_id,
            phase=self.phase,
            round=self.round,
            rules=GameRules(
                player_count=len(self.seats),
                imposter_count=self.config.imposter_count,
                clue_rounds=self.config.clue_rounds,
                discussion_rounds=self.config.discussion_rounds,
                statement_word_cap=self.config.statement_word_cap,
                reasoning_word_cap=self.config.reasoning_word_cap,
            ),
            seat=seat,
            name=assignment.name,
            role=assignment.role,
            word=self.secret.word if not is_imposter or reveal is not None else None,
            hint=self.secret.hint if is_imposter and self.config.imposter_hint else None,
            category=self.secret.category if public_category else None,
            players=self.public_seats(),
            clues=list(self._clues),
            statements=list(self._statements),
            vote_result=self._vote_result,
            reveal=reveal,
            scratchpad=scratchpad,
        )

    def emit[EventT: GameEventBase](
        self, event_type: type[EventT], **fields: Any
    ) -> EventT:
        """Append an event in the current phase and round to the event log.

        Args:
            event_type: The event class.
            **fields: The fields of the event besides the shared ones.

        Returns:
            The appended event.
        """
        event = event_type(
            game_id=self.game_id,
            seq=len(self._events),
            phase=self._step.phase,
            round=self._step.round,
            **fields,
        )
        self._events.append(event)

        return event

    def _require_turn(self, *, seat: int, phase: GamePhase) -> None:
        """Check that a seat has a started turn in the given phase.

        Args:
            seat: The seat about to act.
            phase: The phase the action belongs to.

        Raises:
            InvalidActionError: When the game is in another phase or the seat has no
                started turn.
        """
        if self.phase is not phase:
            message = f"cannot act in phase {phase} while the game is in {self.phase}"
            raise InvalidActionError(message)

        if seat not in self._started:
            message = f"seat {seat} has no started turn in phase {phase}"
            raise InvalidActionError(message)

    def _current_round(self) -> int:
        """Get the round of the current clue or discussion phase.

        Returns:
            The 1-based round.
        """
        if self.round is None:
            message = f"phase {self.phase} has no rounds"
            raise InvalidActionError(message)

        return self.round

    def _truncate_reasoning(self, reasoning: str) -> tuple[str, bool]:
        """Cut private reasoning down to the cap.

        Args:
            reasoning: The reasoning.

        Returns:
            The possibly shortened reasoning and whether words were removed.
        """
        return truncate_words(reasoning, cap=self.config.reasoning_word_cap)

    def _remember(self, *, seat: int, action: str, reasoning: str) -> None:
        """Append a turn to the private scratchpad of a seat.

        Args:
            seat: The seat.
            action: The public action, in a few words.
            reasoning: The private reasoning of the turn.
        """
        self._scratchpads[seat].append(
            ScratchpadEntry(
                phase=self.phase,
                round=self.round,
                action=action,
                private_reasoning=reasoning,
            )
        )

    def _complete_turn(self, seat: int) -> None:
        """Finish the turn of a seat and advance when the phase is complete.

        Args:
            seat: The seat whose turn is complete.
        """
        self._pending.remove(seat)
        self._started.discard(seat)

        if not self._pending:
            self._advance()

    def _advance(self) -> None:
        """Move to the next phase, playing the phases that need no player actions."""
        while True:
            self._step = self._step.following(self.config)

            if self.phase is GamePhase.DONE:
                self.emit(GameFinishedEvent, outcome=self._outcome)
                return

            self.emit(PhaseStartedEvent)

            match self.phase:
                case GamePhase.RESOLUTION:
                    self._resolve_votes()
                case GamePhase.OUTCOME:
                    self._decide_outcome()
                case GamePhase.GUESS:
                    self._pending = self.imposters
                    return
                case _:
                    self._pending = [seat.seat for seat in self.seats]
                    return

    def _resolve_votes(self) -> None:
        """Reveal and tally the votes and decide who is caught."""
        counts = count_votes(self._votes.values())
        caught = caught_seats(counts=counts, catch_count=self.config.imposter_count)
        votes = [
            PublicVote(voter=voter, target=self._votes.get(voter))
            for voter in range(len(self.seats))
        ]
        self._vote_result = VoteResult(votes=votes, caught=caught)
        self.emit(
            VotesRevealedEvent,
            votes=votes,
            counts=[counts[seat] for seat in range(len(self.seats))],
            caught=caught,
        )

    def _decide_outcome(self) -> None:
        """Decide the winner from who was caught and the guesses."""
        caught = self._vote_result.caught if self._vote_result else []
        imposters = self.imposters

        if any(seat not in caught for seat in imposters):
            outcome = GameOutcome.IMPOSTER_WINS
        elif any(
            self._guesses[seat].correct for seat in imposters if seat in self._guesses
        ):
            outcome = GameOutcome.IMPOSTER_STEALS
        else:
            outcome = GameOutcome.CIVILIANS_WIN

        self._outcome = outcome
        self.emit(
            OutcomeEvent,
            outcome=outcome,
            word=self.secret.word,
            imposters=imposters,
            caught=caught,
        )

    def _reveal(self) -> GameReveal | None:
        """Build the reveal once the outcome is decided.

        Returns:
            The word, roles, guesses and outcome, or `None` before the outcome.
        """
        if self._outcome is None:
            return None

        return GameReveal(
            word=self.secret.word,
            category=self.secret.category,
            imposters=self.imposters,
            guesses=[self._guesses[seat] for seat in sorted(self._guesses)],
            outcome=self._outcome,
        )
