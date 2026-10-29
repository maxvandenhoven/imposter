class GameError(Exception):
    """Base class for all errors raised by the game engine."""


class GameSetupError(GameError):
    """Raised when a game cannot be created from a config and secret word."""


class InvalidActionError(GameError):
    """Raised when an action is not allowed in the current game state."""
