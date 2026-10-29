from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class JudgeVerdict(BaseModel):
    """The decision of a judge on a guess or a clue.

    Attributes:
        verdict: `True` when the guess is the secret word, or when the clue is valid.
        confidence: How sure the judge is, from 0 to 1.
        rationale: A short explanation of the decision.
        judge_model: Who decided: `code` for the code checks, otherwise the catalog id of
            the model.
    """

    model_config = ConfigDict(frozen=True)

    verdict: bool
    confidence: float = Field(ge=0, le=1)
    rationale: str
    judge_model: str


class JudgeProtocol(Protocol):
    """Decides what the code rules of the engine cannot: synonyms and derivatives."""

    async def is_same_word(self, guess: str, word: str) -> JudgeVerdict:
        """Decide whether a guess names the secret word.

        Args:
            guess: The guess of an imposter.
            word: The secret word.

        Returns:
            The verdict, `True` when the guess is the same word.
        """
        ...

    async def is_valid_clue(self, clue: str, word: str) -> JudgeVerdict:
        """Decide whether a clue is allowed, that is not a trivial derivative of the word.

        Args:
            clue: The one-word clue.
            word: The secret word.

        Returns:
            The verdict, `True` when the clue is valid.
        """
        ...
