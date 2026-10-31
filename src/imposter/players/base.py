from typing import Protocol

from google.adk.agents.context import Context
from pydantic import BaseModel, ConfigDict, Field

from imposter.config import GamePhase
from imposter.engine.views import PlayerView

REASONING_DESCRIPTION = "Your private reasoning, which nobody else sees."
"""The schema description of the `private_reasoning` field of every response."""


class ClueResponse(BaseModel):
    """The structured output of a clue turn.

    Attributes:
        clue: Exactly one word that is not the secret word.
        private_reasoning: Why this clue, at most the reasoning word cap.
    """

    clue: str = Field(description="Your clue, exactly one word.")
    private_reasoning: str = Field(default="", description=REASONING_DESCRIPTION)


class DiscussionResponse(BaseModel):
    """The structured output of a discussion turn.

    Attributes:
        statement: The public statement, at most the statement word cap.
        private_reasoning: Why this statement, at most the reasoning word cap.
    """

    statement: str = Field(description="Your public statement.")
    private_reasoning: str = Field(default="", description=REASONING_DESCRIPTION)


class VoteResponse(BaseModel):
    """The structured output of a vote turn.

    Attributes:
        vote_for: The display name of another player.
        private_reasoning: Why this vote, at most the reasoning word cap.
    """

    vote_for: str = Field(description="The exact name of the player you vote for.")
    private_reasoning: str = Field(default="", description=REASONING_DESCRIPTION)


class GuessResponse(BaseModel):
    """The structured output of an imposter's guess.

    Attributes:
        guess: The guessed secret word.
        private_reasoning: Why this guess, at most the reasoning word cap.
    """

    guess: str = Field(description="Your guess at the secret word, one word.")
    private_reasoning: str = Field(default="", description=REASONING_DESCRIPTION)


class DebriefResponse(BaseModel):
    """The structured output of a debrief turn.

    Attributes:
        reflection: A reflection on the player's clues, statements and vote.
    """

    reflection: str = Field(description="Your reflection on how you played.")


type PhaseResponse = (
    ClueResponse | DiscussionResponse | VoteResponse | GuessResponse | DebriefResponse
)
"""The structured output of any phase."""

PHASE_RESPONSE_TYPES: dict[GamePhase, type[PhaseResponse]] = {
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


class PlayerResponse(BaseModel):
    """The result of one turn: the structured output plus how it was produced.

    Attributes:
        output: The structured output for the phase, `None` when the player gave up,
            so the runner applies the fallback of the phase.
        usage: The tokens the turn used, if known.
        error: What went wrong, when the player gave up or fell back to a default.
    """

    model_config = ConfigDict(frozen=True)

    output: PhaseResponse | None
    usage: TurnUsage | None = None
    error: str | None = None


class PlayerProtocol(Protocol):
    """A participant in a game, backed by a model, a script or chance.

    A player gets only the view of its own seat, so it cannot see more than the rules
    allow. Which phase to act in and the limits are part of the view. In the game
    workflow a turn runs in the turn node of its seat, whose context a player may use to
    run ADK agents as child nodes of the turn.
    """

    async def take_turn(
        self,
        view: PlayerView,
        retry_reason: str | None = None,
        ctx: Context | None = None,
    ) -> PlayerResponse:
        """Act in the phase of the view.

        Args:
            view: Everything the seat may know.
            retry_reason: Why the previous attempt in this turn was rejected, if any.
            ctx: The context of the turn node, `None` outside the game workflow.

        Returns:
            The structured output of the turn.
        """
        ...
