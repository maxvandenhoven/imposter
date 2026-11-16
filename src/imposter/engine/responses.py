from pydantic import BaseModel, Field

from imposter.config import GamePhase

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
