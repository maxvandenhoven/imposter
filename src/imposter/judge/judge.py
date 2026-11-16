import os
from typing import Self

from google.adk.labs.classifiers import (
    BaseClassifier,
    Binary,
    BinaryAnswer,
    LlmClassifier,
)
from google.genai import types
from opentelemetry.trace import Span

from imposter.judge.base import JudgeVerdict
from imposter.judge.checks import clue_check, same_word_check
from imposter.judge.decisions import API_KEY_ENV, GeminiDecisionsClassifier
from imposter.models.catalog import ModelCatalog
from imposter.models.factory import adk_model
from imposter.telemetry.spans import judge_span

JUDGE_MODEL_ID = "gemini-flash-lite"
"""The catalog id of the model that judges when the Gemini Decisions API has no key."""

VERDICT_THRESHOLD = 0.5
"""The probability from which the answer to a question of the judge counts as yes."""

QUESTION_NAME = "answer"
"""The name of the one question of each call to the classifier."""

SAME_WORD_QUESTION = Binary(
    instructions=(
        "The input holds the secret word of a word game and the guess of a player. "
        "Does the guess name the same thing as the secret word?"
    ),
    criteria=(
        "Synonyms, spelling variants, other grammatical forms and translations name "
        "the same thing. Related but different ideas do not."
    ),
)
"""Asked about a guess that is not an exact match."""

DERIVATIVE_CLUE_QUESTION = Binary(
    instructions=(
        "The input holds the secret word of a word game and the one-word clue of a "
        "player. Is the clue a trivial derivative of the secret word?"
    ),
    criteria=(
        "Another form of the secret word, a compound or word that contains it, a "
        "direct synonym or a translation. An association, however strong, is not."
    ),
)
"""Asked about a clue that passed the code checks. A yes makes the clue invalid."""


class Judge:
    """Decides what the code rules of the engine cannot: synonyms and derivatives.

    The cheap code checks run first, so only cases they cannot decide reach a model
    (README D25). The model sits behind ADK's classifier interface (`BaseClassifier`):
    it gets the facts as input and one yes or no question (`Binary`), and answers
    with the probability of a yes instead of text. Any classifier works: the Gemini
    Decisions API, a model built for such questions, or `LlmClassifier`, which asks a
    regular model. When the classifier fails or declines, the judge falls back to the
    lenient answer, the clue is valid and the guess is not the word, with confidence 0.

    Attributes:
        classifier: The classifier that answers the questions.
        threshold: The probability from which an answer counts as yes.
    """

    def __init__(
        self, classifier: BaseClassifier, *, threshold: float = VERDICT_THRESHOLD
    ) -> None:
        """Initialize the judge.

        Args:
            classifier: The classifier that answers the questions.
            threshold: The probability from which an answer counts as yes.
        """
        self.classifier = classifier
        self.threshold = threshold

    @classmethod
    def load(cls) -> Self:
        """Build the judge on the Gemini Decisions API, or on Gemini Flash-Lite.

        The Decisions API is used when its API key is set (`GEMINI_API_KEY`). Without
        the key the same questions go to Gemini Flash-Lite on Vertex AI at temperature
        0, so the game also runs with Google Cloud credentials alone.

        Returns:
            The judge.
        """
        if os.environ.get(API_KEY_ENV):
            return cls(GeminiDecisionsClassifier())

        entry = ModelCatalog.load().entry(JUDGE_MODEL_ID)
        classifier = LlmClassifier(
            model=adk_model(entry),
            generate_content_config=types.GenerateContentConfig(temperature=0),
        )

        return cls(classifier)

    @property
    def model_name(self) -> str:
        """The name of the model of the classifier, the `judge_model` of its verdicts."""
        model = self.classifier.model

        return model if isinstance(model, str) else model.model

    async def is_same_word(self, *, guess: str, word: str) -> JudgeVerdict:
        """Decide whether a guess names the secret word.

        Args:
            guess: The guess of an imposter.
            word: The secret word.

        Returns:
            The verdict, `True` when the guess is the same word.
        """
        with judge_span(kind="guess") as span:
            verdict = same_word_check(guess=guess, word=word) or await self.ask(
                question=SAME_WORD_QUESTION,
                facts={"secret_word": word, "guess": guess},
                verdict_of_yes=True,
            )
            record_verdict(span=span, verdict=verdict)

        return verdict

    async def is_valid_clue(self, *, clue: str, word: str) -> JudgeVerdict:
        """Decide whether a clue is allowed, that is not a trivial derivative of the word.

        Args:
            clue: The one-word clue.
            word: The secret word.

        Returns:
            The verdict, `True` when the clue is valid.
        """
        with judge_span(kind="clue") as span:
            verdict = clue_check(clue=clue, word=word) or await self.ask(
                question=DERIVATIVE_CLUE_QUESTION,
                facts={"secret_word": word, "clue": clue},
                verdict_of_yes=False,
            )
            record_verdict(span=span, verdict=verdict)

        return verdict

    async def ask(
        self, *, question: Binary, facts: dict[str, str], verdict_of_yes: bool
    ) -> JudgeVerdict:
        """Ask the classifier one question and turn its probability into a verdict.

        Args:
            question: The yes or no question.
            facts: The input the question is about.
            verdict_of_yes: The verdict when the answer is yes. The lenient verdict,
                given when the classifier fails or declines, is the opposite.

        Returns:
            The verdict, with the classifier's confidence when it reports one and the
            distance of the probability from a coin flip otherwise.
        """
        try:
            response = await self.classifier.classify(
                input=facts, questions={QUESTION_NAME: question}
            )
            answer = response.answers[QUESTION_NAME]

            if not isinstance(answer, BinaryAnswer):
                message = f"The classifier gave a {answer.type} answer."
                raise TypeError(message)  # noqa: TRY301
        except Exception as error:
            return JudgeVerdict(
                verdict=not verdict_of_yes,
                confidence=0.0,
                rationale=f"The judge failed, so the lenient verdict applies: {error}",
                judge_model=self.model_name,
            )

        probability = answer.probability
        is_yes = probability >= self.threshold
        confidence = answer.confidence

        if confidence is None:
            confidence = max(probability, 1 - probability)

        return JudgeVerdict(
            verdict=verdict_of_yes if is_yes else not verdict_of_yes,
            confidence=confidence,
            rationale=(
                f"The probability of a yes is {probability:.2f}, against a threshold "
                f"of {self.threshold:.2f}."
            ),
            judge_model=self.model_name,
        )


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
            "imposter.judge.rationale": verdict.rationale,
            "gen_ai.request.model": verdict.judge_model,
        }
    )
