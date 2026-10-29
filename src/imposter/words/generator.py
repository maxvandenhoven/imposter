from collections.abc import Collection

from google.adk.models import BaseLlm
from pydantic import BaseModel, ConfigDict, Field

from imposter.models.catalog import ModelCatalog, ModelCatalogEntry
from imposter.models.structured import StructuredTaskAgent

GENERATOR_MODEL_ID = "gemini-flash-lite"
"""The catalog id of the default generator model."""

GENERATOR_MAX_OUTPUT_TOKENS = 200
"""The answer tokens of one generated word: the JSON with three short fields."""

GENERATOR_INSTRUCTION = """\
You pick secret words for Imposter, a social deduction word game. Civilians know the word
and give one-word clues, the imposter does not and must blend in. Good words are familiar
to everyone but hard to pin down from a single clue: abstract or many-sided words such as
emotions, ideas, sensations, sounds, customs or natural phenomena, which allow many
different clever clues. Avoid obscure words and very concrete objects. The hint is a
related single word that helps an imposter blend in without giving the word away: never
the word itself, a form of it, or a direct synonym."""

GENERATE_TASK = """\
Pick one secret word (a single word, lowercase), a short abstract category for it, and a
hint. Do not use any of these recent words: {recent}."""

HINT_TASK = """\
Secret word: {word}
Category: {category}

Give the hint for this word."""


class GeneratedWord(BaseModel):
    """The structured answer of the generator when it picks a word.

    Attributes:
        word: The secret word.
        category: A short category for the word.
        hint: A related, non-revealing word for imposters.
    """

    model_config = ConfigDict(frozen=True)

    word: str = Field(min_length=1)
    category: str = Field(min_length=1)
    hint: str = Field(min_length=1)


class GeneratedHint(BaseModel):
    """The structured answer of the generator when it only gives a hint.

    Attributes:
        hint: A related, non-revealing word for imposters.
    """

    model_config = ConfigDict(frozen=True)

    hint: str = Field(min_length=1)


class WordGenerator:
    """Generates secret words and imposter hints with Gemini Flash-Lite ("surprise me").

    Attributes:
        word_agent: The ADK agent that picks a word, category and hint.
        hint_agent: The ADK agent that gives the hint for a known word.
    """

    def __init__(
        self, *, entry: ModelCatalogEntry | None = None, model: BaseLlm | None = None
    ) -> None:
        """Initialize the generator.

        Args:
            entry: The catalog entry of the model, Gemini Flash-Lite when not given.
            model: The ADK model object, built from the entry when not given.
        """
        entry = entry or ModelCatalog.load().entry(GENERATOR_MODEL_ID)
        self.word_agent = StructuredTaskAgent(
            name="word_generator",
            entry=entry,
            instruction=GENERATOR_INSTRUCTION,
            response_type=GeneratedWord,
            max_output_tokens=GENERATOR_MAX_OUTPUT_TOKENS,
            model=model,
        )
        self.hint_agent = StructuredTaskAgent(
            name="hint_generator",
            entry=entry,
            instruction=GENERATOR_INSTRUCTION,
            response_type=GeneratedHint,
            max_output_tokens=GENERATOR_MAX_OUTPUT_TOKENS,
            model=model,
        )

    async def generate(self, avoid: Collection[str]) -> GeneratedWord:
        """Generate a new secret word with its category and hint.

        Args:
            avoid: Recently used words that must not be picked.

        Returns:
            The word, category and hint.
        """
        recent = ", ".join(sorted(avoid)) or "none"

        return await self.word_agent.answer(GENERATE_TASK.format(recent=recent))

    async def hint(self, *, word: str, category: str | None) -> str:
        """Generate the imposter hint for a typed or picked word.

        Args:
            word: The secret word.
            category: The category of the word, if known.

        Returns:
            The hint.
        """
        task = HINT_TASK.format(word=word, category=category or "unknown")
        answer = await self.hint_agent.answer(task)

        return answer.hint
