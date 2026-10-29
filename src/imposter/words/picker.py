import random
from collections import deque
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field

CATEGORIES_DIR = Path(__file__).with_name("categories")
"""The built-in word categories, one YAML file per category."""

RECENT_WORD_LIMIT = 50
"""How many recently used words the picker remembers and avoids."""


class WordCategory(BaseModel):
    """A built-in category of secret words.

    Attributes:
        name: The category name, the stem of its YAML file.
        description: What the words of the category have in common.
        words: The words, each one word with optional internal hyphens.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    description: str
    words: list[str] = Field(min_length=1)


class WordPicker:
    """Picks random secret words from the built-in categories, avoiding recent words.

    Attributes:
        categories: The categories by name, in alphabetical order.
        rng: The random generator, seeded for reproducible picks.
        recent: The most recently used words, oldest first, also avoided by the
            generator.
    """

    def __init__(
        self, *, categories: list[WordCategory], seed: int | None = None
    ) -> None:
        """Initialize the picker.

        Args:
            categories: The categories to pick from.
            seed: An optional seed for reproducible picks.
        """
        self.categories = {category.name: category for category in categories}
        self.rng = random.Random(seed)
        self.recent: deque[str] = deque(maxlen=RECENT_WORD_LIMIT)

    @classmethod
    def load(cls, *, directory: Path = CATEGORIES_DIR, seed: int | None = None) -> Self:
        """Load the categories from a directory of YAML files.

        Args:
            directory: The directory, the built-in categories by default.
            seed: An optional seed for reproducible picks.

        Returns:
            The picker.
        """
        categories = [
            WordCategory(name=path.stem, **yaml.safe_load(path.read_text()))
            for path in sorted(directory.glob("*.yaml"))
        ]

        return cls(categories=categories, seed=seed)

    def category(self, name: str) -> WordCategory:
        """Look up a category by name.

        Args:
            name: The category name.

        Returns:
            The category.

        Raises:
            KeyError: When there is no category with the name.
        """
        if name not in self.categories:
            message = f"There is no word category named {name!r}."
            raise KeyError(message)

        return self.categories[name]

    def pick(self, category: str | None = None) -> tuple[str, str]:
        """Pick a random word that was not used recently and remember it.

        When every word of the category was used recently, any word may be picked.

        Args:
            category: The category name, a random category when not given.

        Returns:
            The word and the name of its category.
        """
        name = category or self.rng.choice(sorted(self.categories))
        words = self.category(name).words
        fresh = [word for word in words if word not in self.recent]
        word = self.rng.choice(fresh or words)
        self.remember(word)

        return word, name

    def remember(self, word: str) -> None:
        """Add a word to the recently used words.

        Args:
            word: The word.
        """
        self.recent.append(word.lower())
