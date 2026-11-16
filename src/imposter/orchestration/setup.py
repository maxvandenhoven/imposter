from pydantic import BaseModel, ConfigDict

from imposter.config import GameConfig
from imposter.words.options import WordOptions

DEFAULT_MODEL_IDS = ["gemini-flash", "claude-haiku", "mistral-small", "gemini-flash-lite"]
"""The default lineup: models of three families, cheap enough for a quick game."""


class GameRequest(BaseModel):
    """Everything needed to start a game: the options and how to choose the word.

    Attributes:
        config: The game options.
        words: How the secret word is chosen.
    """

    model_config = ConfigDict(frozen=True)

    config: GameConfig
    words: WordOptions = WordOptions()
