from collections.abc import Sequence
from typing import Self

from pydantic import BaseModel, ConfigDict

from imposter.config import GameConfig, PlayerConfig
from imposter.engine.game import Game
from imposter.judge.base import JudgeProtocol
from imposter.judge.llm_judge import LlmJudge
from imposter.models.catalog import ModelCatalog
from imposter.orchestration.runner import GameRunner
from imposter.players.adk_player import AdkPlayer
from imposter.words.generator import WordGenerator
from imposter.words.options import SecretWordResolver, WordOptions
from imposter.words.picker import WordPicker

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


class GameSetup:
    """Sets up new games: chooses the secret word, creates the game and seats players.

    Attributes:
        catalog: The models that can play a seat.
        resolver: Chooses the secret word.
        judge: Judges clues and guesses, if set.
    """

    def __init__(
        self,
        *,
        catalog: ModelCatalog,
        resolver: SecretWordResolver,
        judge: JudgeProtocol | None = None,
    ) -> None:
        """Initialize the setup.

        Args:
            catalog: The models that can play a seat.
            resolver: Chooses the secret word.
            judge: Judges clues and guesses, if set.
        """
        self.catalog = catalog
        self.resolver = resolver
        self.judge = judge

    @classmethod
    def load(cls, seed: int | None = None) -> Self:
        """Build the setup with the built-in catalog, words and the LLM judge.

        Args:
            seed: An optional seed for reproducible random words.

        Returns:
            The setup.
        """
        resolver = SecretWordResolver(
            picker=WordPicker.load(seed=seed), generator=WordGenerator()
        )

        return cls(catalog=ModelCatalog.load(), resolver=resolver, judge=LlmJudge())

    def player_configs(self, model_ids: Sequence[str]) -> list[PlayerConfig]:
        """Build the seat configs of a lineup, named after the models in the catalog.

        Args:
            model_ids: The catalog ids of the models, one per seat.

        Returns:
            The seat configs, in the given order.

        Raises:
            KeyError: When a model id is not in the catalog.
        """
        entries = [self.catalog.entry(model_id) for model_id in model_ids]

        return [
            PlayerConfig(model_id=entry.id, model_display_name=entry.display_name)
            for entry in entries
        ]

    async def create_game(self, *, request: GameRequest, game_id: str) -> Game:
        """Choose the secret word and create the game.

        Args:
            request: The options and how to choose the word.
            game_id: The id of the game.

        Returns:
            The game, in the first clue round.
        """
        config = request.config
        secret = await self.resolver.resolve(
            options=request.words, with_hint=config.imposter_hint
        )

        return Game.create(config=config, secret=secret, game_id=game_id)

    def runner_for(self, game: Game) -> GameRunner:
        """Seat an ADK player for every seat of a game, with the judge.

        Args:
            game: The game.

        Returns:
            The runner that plays the game.
        """
        players = [
            AdkPlayer(
                entry=self.catalog.entry(seat.player.model_id),
                seat=seat.seat,
                temperature=game.config.temperature,
            )
            for seat in game.seats
        ]

        return GameRunner(players=players, judge=self.judge)
