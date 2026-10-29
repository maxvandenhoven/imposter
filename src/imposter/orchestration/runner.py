import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from imposter.config import GamePhase, PlayerRole
from imposter.engine.game import ActionRejection, Game
from imposter.players.base import (
    ClueResponse,
    DebriefResponse,
    DiscussionResponse,
    GuessResponse,
    PhaseResponse,
    PlayerProtocol,
    TurnUsage,
    VoteResponse,
)

type WordJudge = Callable[[str, str], Awaitable[bool]]
"""A judge that compares a clue or guess with the secret word: `(candidate, word)`."""

MAX_ATTEMPTS = 2
"""Attempts per turn: the first answer plus one retry with the rejection reason."""


class TurnResult(BaseModel):
    """What a player answered in one turn, ready to apply to the game.

    Attributes:
        seat: The seat that took the turn.
        output: The last output of the player, `None` when it gave none.
        rejection: Why the last output was rejected, `None` when it was accepted.
        guess_verdict: The judge's verdict on an inexact guess, if one was asked.
        usages: The tokens every attempt used.
        errors: What went wrong during the turn, for `player_error` events.
    """

    model_config = ConfigDict(frozen=True)

    seat: int
    output: PhaseResponse | None = None
    rejection: ActionRejection | None = None
    guess_verdict: bool | None = None
    usages: list[TurnUsage] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class GameRunner:
    """Runs a game: asks the players for their actions and applies them to the game.

    Asking is the only step that does I/O, and it never changes the game. Applying is
    plain engine calls. In sequential phases one seat is asked at a time. In parallel
    phases (votes and debrief) every pending seat is asked at once, against the same
    game, and the answers are applied in seat order, so the event log does not depend on
    which model answered first. The ADK `GameRunnerAgent` uses the same methods.

    Attributes:
        players: The player at each seat, in seat order.
        clue_judge: Decides whether a clue that passed the code checks is valid, if set.
        guess_judge: Decides whether a guess that is not an exact match is the word, if
            set.
    """

    players: Sequence[PlayerProtocol]
    clue_judge: WordJudge | None = None
    guess_judge: WordJudge | None = None

    async def play(self, game: Game) -> None:
        """Play a game until it is done or aborted.

        Args:
            game: The game, freshly created. It is changed in place.
        """
        while not game.is_over:
            await self.play_step(game)

    async def play_step(self, game: Game) -> None:
        """Play the next turn, or all turns of a parallel phase.

        Args:
            game: The game, not over. It is changed in place.
        """
        seats = game.pending_seats[:1] if game.is_sequential else game.pending_seats

        for seat in seats:
            game.start_turn(seat)

        results = await asyncio.gather(
            *(self.ask(game=game, seat=seat) for seat in seats)
        )

        for result in results:
            self.apply(game=game, result=result)

    async def ask(self, *, game: Game, seat: int) -> TurnResult:
        """Ask the player of a seat for its action, with one retry when it is invalid.

        Args:
            game: The game, with the seat's turn started. It is not changed.
            seat: The seat to ask.

        Returns:
            The answer of the player, with its usage and errors.
        """
        view = game.view_for(seat)
        output: PhaseResponse | None = None
        rejection: ActionRejection | None = None
        usages: list[TurnUsage] = []
        errors: list[str] = []

        for _ in range(MAX_ATTEMPTS):
            try:
                response = await self.players[seat].take_turn(
                    view=view, retry_reason=rejection.reason if rejection else None
                )
            except Exception as error:
                errors.append(f"player failed: {error}")
                break

            if response.usage is not None:
                usages.append(response.usage)

            if response.error:
                errors.append(response.error)

            output = response.output

            if output is None:
                break

            rejection = await self.rejection(game=game, seat=seat, output=output)

            if rejection is None or not rejection.retryable:
                break

        guess_verdict = None

        if (
            isinstance(output, GuessResponse)
            and rejection is None
            and self.guess_judge is not None
            and output.guess.strip()
            and not game.guess_is_exact(output.guess)
        ):
            guess_verdict = await self.guess_judge(output.guess, game.secret.word)

        return TurnResult(
            seat=seat,
            output=output,
            rejection=rejection,
            guess_verdict=guess_verdict,
            usages=usages,
            errors=errors,
        )

    async def rejection(
        self, *, game: Game, seat: int, output: PhaseResponse
    ) -> ActionRejection | None:
        """Check an output against the rules of the current phase and the clue judge.

        Args:
            game: The game.
            seat: The seat that gave the output.
            output: The structured output.

        Returns:
            Why the output is invalid, or `None` when it is valid.
        """
        match game.phase, output:
            case GamePhase.CLUE, ClueResponse(clue=clue):
                rejection = game.clue_rejection(seat=seat, clue=clue)

                if rejection is not None or self.clue_judge is None:
                    return rejection

                if await self.clue_judge(clue, game.secret.word):
                    return None

                # Telling an imposter why would hint at the word, so it just passes.
                return ActionRejection(
                    reason="the clue is too close to the secret word",
                    retryable=game.seats[seat].role is not PlayerRole.IMPOSTER,
                )
            case GamePhase.VOTE, VoteResponse(vote_for=vote_for):
                return game.vote_rejection(voter=seat, vote_for=vote_for)
            case (
                (GamePhase.DISCUSSION, DiscussionResponse())
                | (GamePhase.GUESS, GuessResponse())
                | (GamePhase.DEBRIEF, DebriefResponse())
            ):
                return None
            case phase, _:
                return ActionRejection(
                    reason=f"expected a response for the {phase} phase"
                )

    def apply(self, *, game: Game, result: TurnResult) -> None:
        """Apply the answer of a player to the game.

        Usage is recorded first, because the tokens were spent even when the game is
        aborted for going over the budget. A rejected or missing output becomes the
        fallback action of the phase: pass, silence, abstain, no guess or no reflection.

        Args:
            game: The game, with the seat's turn started. It is changed in place.
            result: The answer of the player.
        """
        seat = result.seat

        for usage in result.usages:
            game.record_usage(
                seat=seat,
                model_id=usage.model_id,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                thinking_tokens=usage.thinking_tokens,
            )

        if game.is_over:
            return

        for message in result.errors:
            game.record_player_error(seat=seat, message=message)

        if result.rejection is not None:
            message = f"invalid action, falling back: {result.rejection.reason}"
            game.record_player_error(seat=seat, message=message)

        accepted = result.output if result.rejection is None else None
        reasoning = getattr(result.output, "private_reasoning", "")

        match game.phase, accepted:
            case GamePhase.CLUE, ClueResponse(clue=clue):
                game.submit_clue(seat=seat, clue=clue, private_reasoning=reasoning)
            case GamePhase.CLUE, _:
                game.submit_clue(
                    seat=seat,
                    clue=None,
                    private_reasoning=reasoning,
                    rejection_reason=result.rejection.reason
                    if result.rejection
                    else None,
                )
            case GamePhase.DISCUSSION, DiscussionResponse(statement=statement):
                game.submit_statement(
                    seat=seat, statement=statement, private_reasoning=reasoning
                )
            case GamePhase.DISCUSSION, _:
                game.submit_statement(
                    seat=seat, statement="", private_reasoning=reasoning
                )
            case GamePhase.VOTE, VoteResponse(vote_for=vote_for):
                game.submit_vote(
                    voter=seat, vote_for=vote_for, private_reasoning=reasoning
                )
            case GamePhase.VOTE, _:
                game.submit_vote(voter=seat, vote_for=None, private_reasoning=reasoning)
            case GamePhase.GUESS, GuessResponse(guess=guess):
                game.submit_guess(
                    seat=seat,
                    guess=guess,
                    private_reasoning=reasoning,
                    judge_verdict=result.guess_verdict,
                )
            case GamePhase.GUESS, _:
                game.submit_guess(seat=seat, guess="", private_reasoning=reasoning)
            case GamePhase.DEBRIEF, DebriefResponse(reflection=reflection):
                game.submit_reflection(seat=seat, reflection=reflection)
            case _:
                game.submit_reflection(seat=seat, reflection="")
