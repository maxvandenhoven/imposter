from typing import Protocol

from imposter.engine.game import Game


class GameStoreProtocol(Protocol):
    """Keeps the games, running and finished, by game id.

    A `Game` changes in place while it is played, so a game is saved once when it is
    created. A persistent store would also save it after every step.
    """

    def save(self, game: Game) -> None:
        """Add a game, or replace the stored game with the same id.

        Args:
            game: The game.
        """
        ...

    def get(self, game_id: str) -> Game | None:
        """Look up a game.

        Args:
            game_id: The game.

        Returns:
            The game, or `None` when the store has no game with the id.
        """
        ...

    def list_recent(self, limit: int = 20) -> list[Game]:
        """List the most recently created games.

        Args:
            limit: The largest number of games to list.

        Returns:
            The games, newest first.
        """
        ...


class InMemoryGameStore:
    """A game store that keeps the games in a dict (README D13).

    Attributes:
        games: The games by id, in the order they were first saved.
    """

    def __init__(self) -> None:
        """Initialize an empty store."""
        self.games: dict[str, Game] = {}

    def save(self, game: Game) -> None:
        """Add a game, or replace the stored game with the same id.

        Args:
            game: The game.
        """
        self.games[game.game_id] = game

    def get(self, game_id: str) -> Game | None:
        """Look up a game.

        Args:
            game_id: The game.

        Returns:
            The game, or `None` when the store has no game with the id.
        """
        return self.games.get(game_id)

    def list_recent(self, limit: int = 20) -> list[Game]:
        """List the most recently created games.

        Args:
            limit: The largest number of games to list.

        Returns:
            The games, newest first.
        """
        return list(reversed(self.games.values()))[:limit]
