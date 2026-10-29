import asyncio
from collections.abc import Awaitable, Callable, Mapping

from imposter.engine.config import GamePhase, PlayerRole
from imposter.engine.state import ActionRejection, GameState
from imposter.players.base import (
    ClueResponse,
    DebriefResponse,
    DiscussionResponse,
    GuessResponse,
    PhaseResponse,
    Player,
    PlayerResponse,
    PlayerTask,
    VoteResponse,
)

type WordJudgeHook = Callable[[str, str], Awaitable[bool]]
"""An injected judge: `(candidate, word) -> verdict`, for clues or guesses."""

MAX_ATTEMPTS = 2
"""Attempts per turn: the first answer plus one retry with the rejection reason."""


class GameDriver:
    """A small driver that plays a whole game with in-process players.

    It mirrors what the `GameMaster` agent does (WP 06) without ADK: sequential phases
    one seat at a time, votes and the debrief in parallel, one retry for invalid actions
    and a fallback after that. It is used by tests and offline demos.

    Attributes:
        state: The game being played.
        players: The player at each seat.
        clue_judge: Decides whether a clue that passed the code checks is valid, if set.
        guess_judge: Decides whether a guess that is not an exact match is the word, if
            set.
    """

    def __init__(
        self,
        *,
        state: GameState,
        players: Mapping[int, Player],
        clue_judge: WordJudgeHook | None = None,
        guess_judge: WordJudgeHook | None = None,
    ) -> None:
        """Initialize the driver.

        Args:
            state: The game to play, freshly created.
            players: The player at each seat.
            clue_judge: Decides whether a clue that passed the code checks is valid.
            guess_judge: Decides whether a guess that is not an exact match is the word.
        """
        self.state = state
        self.players = players
        self.clue_judge = clue_judge
        self.guess_judge = guess_judge

    async def run(self) -> GameState:
        """Play the game until it is done or aborted.

        Returns:
            The finished game.
        """
        while not self.state.is_over:
            pending = self.state.pending_seats

            if self.state.is_sequential:
                await self.play_turn(pending[0])
            else:
                for seat in pending:
                    self.state.start_turn(seat)

                await asyncio.gather(
                    *(self.play_turn(seat, started=True) for seat in pending)
                )

        return self.state

    async def play_turn(self, seat: int, *, started: bool = False) -> None:
        """Play one turn of a seat, with one retry and a fallback.

        Args:
            seat: The seat to play.
            started: Whether the turn was already started by the caller.
        """
        if not started:
            self.state.start_turn(seat)

        player = self.players[seat]
        rejection: ActionRejection | None = None
        last_output: PhaseResponse | None = None

        for _ in range(MAX_ATTEMPTS):
            view = self.state.view_for(seat)
            task = PlayerTask.for_view(
                view, retry_reason=rejection.reason if rejection else None
            )

            try:
                response = await player.take_turn(view=view, task=task)
            except Exception as error:
                self.state.record_player_error(
                    seat=seat, message=f"player failed: {error}"
                )
                break

            self.record_response(seat=seat, response=response)

            if self.state.is_over:
                return

            last_output = response.output
            rejection = await self.rejection(seat=seat, output=response.output)

            if rejection is None:
                await self.submit(seat=seat, output=response.output)
                return

            if not rejection.retryable:
                break

        if rejection is not None:
            message = f"invalid action, falling back: {rejection.reason}"
            self.state.record_player_error(seat=seat, message=message)

        self.submit_fallback(
            seat=seat,
            last_output=last_output,
            reason=rejection.reason if rejection else None,
        )

    def record_response(self, *, seat: int, response: PlayerResponse) -> None:
        """Record the usage and any player error that came with a response.

        Args:
            seat: The seat that responded.
            response: The response.
        """
        if response.error:
            self.state.record_player_error(seat=seat, message=response.error)

        if response.usage is not None:
            self.state.record_usage(
                seat=seat,
                model_id=response.usage.model_id,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                thinking_tokens=response.usage.thinking_tokens,
            )

    async def rejection(
        self, *, seat: int, output: PhaseResponse
    ) -> ActionRejection | None:
        """Check an output against the rules of the current phase and the judge.

        Args:
            seat: The seat that gave the output.
            output: The structured output.

        Returns:
            Why the output is invalid, or `None` when it is valid.
        """
        match self.state.phase, output:
            case GamePhase.CLUE, ClueResponse(clue=clue):
                code_rejection = self.state.clue_rejection(seat=seat, clue=clue)

                if code_rejection is not None:
                    return code_rejection

                if self.clue_judge and not await self.clue_judge(
                    clue, self.state.secret.word
                ):
                    # Telling an imposter why would hint at the word, so it just passes.
                    is_imposter = self.state.seats[seat].role is PlayerRole.IMPOSTER

                    return ActionRejection(
                        reason="the clue is too close to the secret word",
                        retryable=not is_imposter,
                    )

                return None
            case GamePhase.VOTE, VoteResponse(vote_for=vote_for):
                return self.state.vote_rejection(voter=seat, vote_for=vote_for)
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

    async def submit(self, *, seat: int, output: PhaseResponse) -> None:
        """Submit a valid output to the game.

        Args:
            seat: The seat that gave the output.
            output: The structured output, valid for the current phase.
        """
        match output:
            case ClueResponse():
                self.state.submit_clue(
                    seat=seat,
                    clue=output.clue,
                    private_reasoning=output.private_reasoning,
                )
            case DiscussionResponse():
                self.state.submit_statement(
                    seat=seat,
                    statement=output.statement,
                    private_reasoning=output.private_reasoning,
                )
            case VoteResponse():
                self.state.submit_vote(
                    voter=seat,
                    vote_for=output.vote_for,
                    private_reasoning=output.private_reasoning,
                )
            case GuessResponse():
                verdict = None

                if self.guess_judge and not self.state.guess_is_exact(output.guess):
                    verdict = await self.guess_judge(output.guess, self.state.secret.word)

                self.state.submit_guess(
                    seat=seat,
                    guess=output.guess,
                    private_reasoning=output.private_reasoning,
                    judge_verdict=verdict,
                )
            case DebriefResponse():
                self.state.submit_reflection(seat=seat, reflection=output.reflection)

    def submit_fallback(
        self, *, seat: int, last_output: PhaseResponse | None, reason: str | None
    ) -> None:
        """Submit the fallback action of the phase: pass, silence, abstain or no guess.

        Args:
            seat: The seat.
            last_output: The last invalid output, whose reasoning is kept if it has any.
            reason: Why the last output was rejected, if it was.
        """
        reasoning = getattr(last_output, "private_reasoning", "")

        match self.state.phase:
            case GamePhase.CLUE:
                self.state.submit_clue(
                    seat=seat,
                    clue=None,
                    private_reasoning=reasoning,
                    rejection_reason=reason or None,
                )
            case GamePhase.DISCUSSION:
                self.state.submit_statement(
                    seat=seat, statement="", private_reasoning=reasoning
                )
            case GamePhase.VOTE:
                self.state.submit_vote(
                    voter=seat, vote_for=None, private_reasoning=reasoning
                )
            case GamePhase.GUESS:
                self.state.submit_guess(seat=seat, guess="", private_reasoning=reasoning)
            case GamePhase.DEBRIEF:
                self.state.submit_reflection(seat=seat, reflection="")
