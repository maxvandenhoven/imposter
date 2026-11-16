from pydantic import BaseModel, ConfigDict, Field


class JudgeVerdict(BaseModel):
    """The decision of the judge on a guess or a clue.

    Attributes:
        verdict: `True` when the guess is the secret word, or when the clue is valid.
        confidence: How sure the judge is, from 0 to 1.
        rationale: A short explanation of the decision.
        judge_model: Who decided: `code` for the code checks, otherwise the name of the
            model of the classifier.
    """

    model_config = ConfigDict(frozen=True)

    verdict: bool
    confidence: float = Field(ge=0, le=1)
    rationale: str
    judge_model: str
