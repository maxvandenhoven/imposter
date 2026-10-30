from google.adk.models import BaseLlm
from opentelemetry.trace import Span
from pydantic import BaseModel, ConfigDict, Field

from imposter.judge.base import JudgeVerdict
from imposter.judge.checks import clue_check, same_word_check
from imposter.models.catalog import ModelCatalog, ModelCatalogEntry
from imposter.models.structured import StructuredTaskAgent
from imposter.telemetry.spans import judge_span

JUDGE_MODEL_ID = "gemini-flash-lite"
"""The catalog id of the default judge model."""

JUDGE_MAX_OUTPUT_TOKENS = 300
"""The answer tokens of one verdict: the JSON with a short rationale."""

JUDGE_INSTRUCTION = """\
You are the referee of a word game. Players know a secret word and give one-word clues
about it, and an imposter tries to guess the word. Answer the question about the word
with a verdict, your confidence from 0 to 1 and a one-sentence rationale. Be strict and
consistent."""

SAME_WORD_TASK = """\
Secret word: {word}
Guess: {guess}

Does the guess name the same thing as the secret word? Count synonyms, spelling
variants, other grammatical forms and translations as the same word. Related but
different ideas are not the same word."""

VALID_CLUE_TASK = """\
Secret word: {word}
Clue: {clue}

Is the clue valid? A clue is invalid when it is a trivial derivative of the secret
word: another form of it, a compound or word that contains it, a direct synonym, or a
translation. Associations, however strong, are valid."""


class JudgeAnswer(BaseModel):
    """The structured answer of the judge model.

    Attributes:
        verdict: The answer to the question.
        confidence: How sure the model is, from 0 to 1.
        rationale: One sentence on why.
    """

    model_config = ConfigDict(frozen=True)

    verdict: bool
    confidence: float = Field(ge=0, le=1)
    rationale: str


class LlmJudge:
    """A judge that runs the code checks first and asks a model only when they fail.

    Only cases the code checks cannot decide reach the model (README D25).
    The model is Gemini Flash-Lite at temperature 0 with structured output. When the
    model fails, the judge falls back to the lenient answer: the clue is valid and the
    guess is not the word, with confidence 0.

    Attributes:
        agent: The ADK agent that asks the model.
    """

    def __init__(
        self, *, entry: ModelCatalogEntry | None = None, model: BaseLlm | None = None
    ) -> None:
        """Initialize the judge.

        Args:
            entry: The catalog entry of the judge model, Gemini Flash-Lite when not
                given.
            model: The ADK model object, built from the entry when not given.
        """
        self.agent = StructuredTaskAgent(
            name="judge",
            entry=entry or ModelCatalog.load().entry(JUDGE_MODEL_ID),
            instruction=JUDGE_INSTRUCTION,
            response_type=JudgeAnswer,
            max_output_tokens=JUDGE_MAX_OUTPUT_TOKENS,
            temperature=0,
            model=model,
        )

    async def is_same_word(self, guess: str, word: str) -> JudgeVerdict:
        """Decide whether a guess names the secret word.

        Args:
            guess: The guess of an imposter.
            word: The secret word.

        Returns:
            The verdict, `True` when the guess is the same word.
        """
        with judge_span(kind="guess") as span:
            verdict = same_word_check(guess=guess, word=word) or await self.verdict(
                task=SAME_WORD_TASK.format(word=word, guess=guess), fallback=False
            )
            record_verdict(span=span, verdict=verdict)

        return verdict

    async def is_valid_clue(self, clue: str, word: str) -> JudgeVerdict:
        """Decide whether a clue is allowed, that is not a trivial derivative of the word.

        Args:
            clue: The one-word clue.
            word: The secret word.

        Returns:
            The verdict, `True` when the clue is valid.
        """
        with judge_span(kind="clue") as span:
            verdict = clue_check(clue=clue, word=word) or await self.verdict(
                task=VALID_CLUE_TASK.format(word=word, clue=clue), fallback=True
            )
            record_verdict(span=span, verdict=verdict)

        return verdict

    async def verdict(self, *, task: str, fallback: bool) -> JudgeVerdict:
        """Ask the model one question.

        Args:
            task: The question.
            fallback: The verdict when the model gives no valid answer.

        Returns:
            The verdict of the model, or the fallback with confidence 0.
        """
        model_id = self.agent.entry.id

        try:
            answer = await self.agent.answer(task)
        except Exception as error:
            return JudgeVerdict(
                verdict=fallback,
                confidence=0.0,
                rationale=f"The judge failed, so the lenient verdict applies: {error}",
                judge_model=model_id,
            )

        return JudgeVerdict(**answer.model_dump(), judge_model=model_id)


def record_verdict(*, span: Span, verdict: JudgeVerdict) -> None:
    """Set a verdict on the span of the judge decision.

    Args:
        span: The span of the decision.
        verdict: The verdict.
    """
    span.set_attributes(
        {
            "imposter.judge.verdict": verdict.verdict,
            "imposter.judge.confidence": verdict.confidence,
            "gen_ai.request.model": verdict.judge_model,
        }
    )
