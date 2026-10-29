from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from imposter.config import SecretWord
from imposter.utils.text import clean_word, is_single_word, mentions_word
from imposter.words.generator import WordGenerator
from imposter.words.picker import WordPicker


class WordMode(StrEnum):
    """How the secret word is chosen."""

    RANDOM = "random"
    TYPED = "typed"
    GENERATED = "generated"


class WordOptions(BaseModel):
    """The word options of the setup screen.

    They are resolved into a `SecretWord` before the game is created.

    Attributes:
        mode: How the word is chosen.
        word: The typed word, required in `typed` mode only.
        category: The category: optional for `typed` and `random` (a random category
            when not given), unused for `generated`.
    """

    model_config = ConfigDict(frozen=True)

    mode: WordMode = WordMode.RANDOM
    word: str | None = None
    category: str | None = None

    @model_validator(mode="after")
    def check_word(self) -> Self:
        """Check that a typed word is given in `typed` mode only, as one word.

        Returns:
            The validated options.

        Raises:
            ValueError: When the typed word is missing, not one word or not expected.
        """
        if self.mode is WordMode.TYPED and not (
            self.word and is_single_word(clean_word(self.word))
        ):
            message = "A typed secret word must be exactly one word."
            raise ValueError(message)

        if self.mode is not WordMode.TYPED and self.word is not None:
            message = f"A secret word can only be typed in mode typed, not {self.mode}."
            raise ValueError(message)

        return self


class SecretWordResolver:
    """Turns the word options into a `SecretWord`, with a hint when the game uses one.

    Attributes:
        picker: Picks random words and remembers the recently used ones.
        generator: Generates words and hints, needed for `generated` mode and hints.
    """

    def __init__(self, *, picker: WordPicker, generator: WordGenerator | None) -> None:
        """Initialize the resolver.

        Args:
            picker: Picks random words and remembers the recently used ones.
            generator: Generates words and hints, if available.
        """
        self.picker = picker
        self.generator = generator

    async def resolve(self, *, options: WordOptions, with_hint: bool) -> SecretWord:
        """Choose the secret word of a new game.

        Args:
            options: The word options of the setup screen.
            with_hint: Whether the game gives imposters a hint.

        Returns:
            The word, its category if known, and the hint when asked for.

        Raises:
            ValueError: When a generator is needed but none is set, or when the hint
                gives the word away.
        """
        hint = None

        match options.mode:
            case WordMode.TYPED:
                word, category = clean_word(options.word or ""), options.category
                self.picker.remember(word)
            case WordMode.RANDOM:
                word, category = self.picker.pick(options.category)
            case WordMode.GENERATED:
                generated = await self.require_generator().generate(self.picker.recent)
                word, category, hint = generated.word, generated.category, generated.hint
                self.picker.remember(word)

        if with_hint and hint is None:
            hint = await self.require_generator().hint(word=word, category=category)

        if hint is not None and mentions_word(hint, word):
            message = f"The generated hint {hint!r} gives the secret word away."
            raise ValueError(message)

        return SecretWord(word=word, category=category, hint=hint if with_hint else None)

    def require_generator(self) -> WordGenerator:
        """Get the generator, which generated words and hints need.

        Returns:
            The generator.

        Raises:
            ValueError: When no generator is set.
        """
        if self.generator is None:
            message = "Generated words and hints need a word generator."
            raise ValueError(message)

        return self.generator
