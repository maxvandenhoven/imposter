from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field

from imposter.engine.config import GamePhase
from imposter.engine.views import PlayerView


class ClueResponse(BaseModel):
    """The structured output of a clue turn.

    Attributes:
        clue: Exactly one word that is not the secret word.
        private_reasoning: Why this clue, at most the reasoning word cap.
    """

    clue: str
    private_reasoning: str = ""


class DiscussionResponse(BaseModel):
    """The structured output of a discussion turn.

    Attributes:
        statement: The public statement, at most the statement word cap.
        private_reasoning: Why this statement, at most the reasoning word cap.
    """

    statement: str
    private_reasoning: str = ""


class VoteResponse(BaseModel):
    """The structured output of a vote turn.

    Attributes:
        vote_for: The display name of another player.
        private_reasoning: Why this vote, at most the reasoning word cap.
    """

    vote_for: str
    private_reasoning: str = ""


class GuessResponse(BaseModel):
    """The structured output of an imposter's guess.

    Attributes:
        guess: The guessed secret word.
        private_reasoning: Why this guess, at most the reasoning word cap.
    """

    guess: str
    private_reasoning: str = ""


class DebriefResponse(BaseModel):
    """The structured output of a debrief turn.

    Attributes:
        reflection: A reflection on the player's clues, statements and vote.
    """

    reflection: str


type PhaseResponse = (
    ClueResponse | DiscussionResponse | VoteResponse | GuessResponse | DebriefResponse
)
"""The structured output of any phase."""

PHASE_RESPONSE_TYPES: dict[GamePhase, type[BaseModel]] = {
    GamePhase.CLUE: ClueResponse,
    GamePhase.DISCUSSION: DiscussionResponse,
    GamePhase.VOTE: VoteResponse,
    GamePhase.GUESS: GuessResponse,
    GamePhase.DEBRIEF: DebriefResponse,
}
"""The response type expected in each phase in which players act."""


class TurnUsage(BaseModel):
    """The tokens one turn used.

    Attributes:
        model_id: The model that used the tokens.
        input_tokens: The prompt tokens.
        output_tokens: The completion tokens.
        thinking_tokens: The thinking tokens.
    """

    model_config = ConfigDict(frozen=True)

    model_id: str
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    thinking_tokens: int = Field(default=0, ge=0)


class PlayerTask(BaseModel):
    """What a player is asked to do in one turn, besides what its view shows.

    Attributes:
        phase: The phase to act in.
        round: The round of the phase, if it has rounds.
        statement_word_cap: The maximum number of words in a statement.
        reasoning_word_cap: The maximum number of words of private reasoning.
        retry_reason: Why the previous attempt in this turn was rejected, if any.
    """

    model_config = ConfigDict(frozen=True)

    phase: GamePhase
    round: int | None
    statement_word_cap: int
    reasoning_word_cap: int
    retry_reason: str | None = None

    @classmethod
    def for_view(cls, view: PlayerView, *, retry_reason: str | None = None) -> Self:
        """Build the task for the phase a view was taken in.

        Args:
            view: The view of the acting seat.
            retry_reason: Why the previous attempt was rejected, if this is a retry.

        Returns:
            The task.
        """
        return cls(
            phase=view.phase,
            round=view.round,
            statement_word_cap=view.rules.statement_word_cap,
            reasoning_word_cap=view.rules.reasoning_word_cap,
            retry_reason=retry_reason,
        )

    @property
    def response_type(self) -> type[BaseModel]:
        """The response type expected for this task."""
        return PHASE_RESPONSE_TYPES[self.phase]


class PlayerResponse(BaseModel):
    """The result of one turn: the structured output plus how it was produced.

    Attributes:
        output: The structured output for the phase.
        usage: The tokens the turn used, if known.
        attempts: The number of model calls the player needed, including retries.
        error: What went wrong, when the player fell back to a default output.
    """

    model_config = ConfigDict(frozen=True)

    output: PhaseResponse
    usage: TurnUsage | None = None
    attempts: int = Field(default=1, ge=1)
    error: str | None = None


class Player(Protocol):
    """A participant in a game, backed by a model, a script or chance.

    Attributes:
        seat: The seat the player sits at.
    """

    seat: int

    async def take_turn(self, view: PlayerView, task: PlayerTask) -> PlayerResponse:
        """Act in the current phase.

        Args:
            view: Everything the seat may know.
            task: The phase to act in and its limits.

        Returns:
            The structured output of the turn.
        """
        ...
