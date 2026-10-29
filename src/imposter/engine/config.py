import random
from collections import Counter
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from imposter.engine.rules import NEUTRAL_NAMES

MIN_PLAYERS = 3
"""The smallest number of seats in a game."""

MAX_PLAYERS = 8
"""The largest number of seats in a game, a cost guardrail (README D29)."""


class IdentityMode(StrEnum):
    """How players are named in views and the public transcript."""

    SEAT = "seat"
    NAMES = "names"
    MODELS = "models"

    def seat_names(self, players: "list[PlayerConfig]", rng: random.Random) -> list[str]:
        """Name the seats of a game under this identity mode.

        Args:
            players: The players in seat order.
            rng: The random number generator of the game, used to pick neutral names.

        Returns:
            The display name of each seat, in seat order.
        """
        match self:
            case IdentityMode.SEAT:
                return [f"Player {seat + 1}" for seat in range(len(players))]
            case IdentityMode.NAMES:
                return rng.sample(NEUTRAL_NAMES, k=len(players))
            case IdentityMode.MODELS:
                labels = [player.model_label for player in players]
                totals = Counter(labels)
                seen: Counter[str] = Counter()
                names = []

                for label in labels:
                    seen[label] += 1
                    names.append(
                        f"{label} #{seen[label]}" if totals[label] > 1 else label
                    )

                return names


class WordMode(StrEnum):
    """How the secret word is chosen at setup."""

    RANDOM = "random"
    TYPED = "typed"
    GENERATED = "generated"


class GamePhase(StrEnum):
    """The phases of a game, in the order they are played."""

    SETUP = "setup"
    CLUE = "clue"
    DISCUSSION = "discussion"
    VOTE = "vote"
    RESOLUTION = "resolution"
    GUESS = "guess"
    OUTCOME = "outcome"
    DEBRIEF = "debrief"
    DONE = "done"
    ABORTED = "aborted"


class PlayerRole(StrEnum):
    """The secret role of a seat."""

    CIVILIAN = "civilian"
    IMPOSTER = "imposter"


class GameOutcome(StrEnum):
    """How a finished game ended."""

    IMPOSTER_WINS = "imposter_wins"
    IMPOSTER_STEALS = "imposter_steals"
    CIVILIANS_WIN = "civilians_win"


class PlayerConfig(BaseModel):
    """The setup of one seat before seat order is randomised.

    Attributes:
        model_id: The catalog id of the model playing this seat.
        model_display_name: The display name of the model, used as the player name in
            `models` identity mode. Falls back to `model_id` when not given.
        persona: An optional persona id, reserved for future work (README D23).
    """

    model_config = ConfigDict(frozen=True)

    model_id: str = Field(min_length=1)
    model_display_name: str | None = None
    persona: str | None = None

    @property
    def model_label(self) -> str:
        """The name of the model shown to players in `models` identity mode."""
        return self.model_display_name or self.model_id


class GameConfig(BaseModel):
    """The options chosen on the setup screen, with the defaults of `game-rules.md`.

    Attributes:
        word_mode: How the secret word is chosen.
        word: The typed secret word, required in `typed` word mode.
        category: The word category, required in `random` word mode.
        players: The seats of the game, 3 to 8.
        imposter_count: The number of imposters, at most `floor((players - 1) / 2)`.
        identity_mode: How players are named.
        public_category: Whether every player, including imposters, learns the category.
        imposter_hint: Whether imposters get a related hint word.
        clue_rounds: The number of clue rounds.
        discussion_rounds: The number of discussion rounds.
        statement_word_cap: The maximum number of words in a discussion statement.
        reasoning_word_cap: The maximum number of words of private reasoning per turn.
        token_budget: The total tokens a game may use before it is aborted.
        temperature: An optional sampling temperature override for every player.
        seed: An optional seed for reproducible seat order, roles and names.
    """

    model_config = ConfigDict(frozen=True)

    word_mode: WordMode = WordMode.RANDOM
    word: str | None = None
    category: str | None = None
    players: list[PlayerConfig] = Field(min_length=MIN_PLAYERS, max_length=MAX_PLAYERS)
    imposter_count: int = Field(default=1, ge=1)
    identity_mode: IdentityMode = IdentityMode.NAMES
    public_category: bool = True
    imposter_hint: bool = False
    clue_rounds: int = Field(default=2, ge=1, le=3)
    discussion_rounds: int = Field(default=2, ge=0, le=3)
    statement_word_cap: int = Field(default=100, ge=1)
    reasoning_word_cap: int = Field(default=60, ge=1)
    token_budget: int = Field(default=200_000, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    seed: int | None = None

    @property
    def max_imposters(self) -> int:
        """The largest allowed number of imposters for the number of seats."""
        return (len(self.players) - 1) // 2

    @model_validator(mode="after")
    def check_consistency(self) -> Self:
        """Check the options that depend on each other.

        Returns:
            The validated config.

        Raises:
            ValueError: When there are too many imposters or the word mode lacks its
                required word or category.
        """
        if self.imposter_count > self.max_imposters:
            message = (
                f"{len(self.players)} players allow at most {self.max_imposters} "
                f"imposters, got {self.imposter_count}"
            )
            raise ValueError(message)

        if self.word_mode is WordMode.TYPED and not self.word:
            message = "typed word mode requires a word"
            raise ValueError(message)

        if self.word_mode is WordMode.RANDOM and not self.category:
            message = "random word mode requires a category"
            raise ValueError(message)

        return self


class SecretWord(BaseModel):
    """The secret word fixed at setup, after the word mode has been resolved.

    Attributes:
        word: The secret word civilians learn.
        category: The category of the word, if known.
        hint: A related word for imposters, if one was generated.
    """

    model_config = ConfigDict(frozen=True)

    word: str = Field(min_length=1)
    category: str | None = None
    hint: str | None = None
