from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MIN_PLAYERS = 3
"""The smallest number of seats in a game."""

MAX_PLAYERS = 8
"""The largest number of seats in a game, a cost guardrail (README D29)."""


class IdentityMode(StrEnum):
    """How players are named in views and the public transcript."""

    SEAT = "seat"
    NAMES = "names"
    MODELS = "models"


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
    """How a finished game ended.

    Saying the secret word in a clue or statement ends the game at once and loses it for
    the speaker's side: the imposters win when a civilian says it (`CIVILIAN_SAID_WORD`)
    and the civilians win when an imposter says it (`IMPOSTER_SAID_WORD`).
    """

    IMPOSTER_WINS = "imposter_wins"
    IMPOSTER_STEALS = "imposter_steals"
    CIVILIANS_WIN = "civilians_win"
    CIVILIAN_SAID_WORD = "civilian_said_word"
    IMPOSTER_SAID_WORD = "imposter_said_word"


class PlayerConfig(BaseModel):
    """The setup of one seat before seat order is randomised.

    Attributes:
        model_id: The catalog id of the model playing this seat.
        model_display_name: The display name of the model, used as the player name in
            `models` identity mode. Falls back to `model_id` when not given.
        persona: An optional persona id, reserved for future work (README D23).
        imposter: Whether this player must be an imposter. Players without it are
            picked at random for the imposter seats that remain.
    """

    model_config = ConfigDict(frozen=True)

    model_id: str = Field(min_length=1)
    model_display_name: str | None = None
    persona: str | None = None
    imposter: bool = False


class GameConfig(BaseModel):
    """The game options chosen on the setup screen, with the defaults of `game-rules.md`.

    How the secret word is chosen is not part of the config: the caller resolves it into
    a `SecretWord` before the game is created.

    Attributes:
        players: The seats of the game, 3 to 8.
        imposter_count: The number of imposters, at most `max_imposters`.
        identity_mode: How players are named.
        public_category: Whether every player, including imposters, learns the category.
        imposter_hint: Whether imposters get a related hint word.
        model_clue_check: Whether a model judges clues that pass the code checks, to
            catch synonyms and translations of the word. Code checks always run.
        clue_rounds: The number of clue rounds.
        discussion_rounds: The number of discussion rounds.
        statement_word_cap: The maximum number of words in a discussion statement.
        reasoning_word_cap: The maximum number of words of private reasoning per turn.
        token_budget: The total tokens a game may use before it is aborted.
        temperature: An optional sampling temperature override for every player.
        seed: An optional seed for reproducible seat order, roles and names.
    """

    model_config = ConfigDict(frozen=True)

    players: list[PlayerConfig] = Field(min_length=MIN_PLAYERS, max_length=MAX_PLAYERS)
    imposter_count: int = Field(default=1, ge=1)
    identity_mode: IdentityMode = IdentityMode.NAMES
    public_category: bool = False
    imposter_hint: bool = False
    model_clue_check: bool = True
    clue_rounds: int = Field(default=2, ge=1, le=3)
    discussion_rounds: int = Field(default=2, ge=0, le=3)
    statement_word_cap: int = Field(default=100, ge=1)
    reasoning_word_cap: int = Field(default=60, ge=1)
    token_budget: int = Field(default=200_000, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    seed: int | None = None

    @model_validator(mode="after")
    def check_imposter_count(self) -> Self:
        """Check that the imposters are a minority and the chosen ones fit their number.

        Returns:
            The validated config.

        Raises:
            ValueError: When there are too many imposters for the number of seats, or
                more players are chosen as imposters than there are imposters.
        """
        allowed = max_imposters(len(self.players))

        if self.imposter_count > allowed:
            message = (
                f"A game with {len(self.players)} players allows at most {allowed} "
                f"imposters, got {self.imposter_count}."
            )
            raise ValueError(message)

        chosen = sum(player.imposter for player in self.players)

        if chosen > self.imposter_count:
            message = (
                f"{chosen} players are chosen as imposters, but the game has only "
                f"{self.imposter_count}."
            )
            raise ValueError(message)

        return self


class SecretWord(BaseModel):
    """The secret word fixed at setup.

    Attributes:
        word: The secret word civilians learn.
        category: The category of the word, if known.
        hint: A related word for imposters, if one was generated.
    """

    model_config = ConfigDict(frozen=True)

    word: str = Field(min_length=1)
    category: str | None = None
    hint: str | None = None


def max_imposters(player_count: int) -> int:
    """Get the largest allowed number of imposters for a number of seats.

    Args:
        player_count: The number of seats.

    Returns:
        The largest number of imposters that is still less than half of the others.
    """
    return (player_count - 1) // 2
