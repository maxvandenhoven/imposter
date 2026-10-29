from typing import Self

from pydantic import BaseModel, ConfigDict

from imposter.engine.config import GameConfig, GamePhase

SEQUENTIAL_PHASES = frozenset({GamePhase.CLUE, GamePhase.DISCUSSION, GamePhase.GUESS})
"""Phases in which players act one at a time, in seat order."""

PARALLEL_PHASES = frozenset({GamePhase.VOTE, GamePhase.DEBRIEF})
"""Phases in which players act simultaneously, without seeing each other's action."""

TERMINAL_PHASES = frozenset({GamePhase.DONE, GamePhase.ABORTED})
"""Phases after which nothing happens anymore."""


class PhaseStep(BaseModel):
    """A phase together with its round number, one step of the game.

    Attributes:
        phase: The phase.
        round: The 1-based round for clue and discussion phases, otherwise `None`.
    """

    model_config = ConfigDict(frozen=True)

    phase: GamePhase
    round: int | None = None

    @property
    def is_sequential(self) -> bool:
        """Whether players act one at a time in this step."""
        return self.phase in SEQUENTIAL_PHASES

    @property
    def is_terminal(self) -> bool:
        """Whether the game is over in this step."""
        return self.phase in TERMINAL_PHASES

    def following(self, config: GameConfig) -> Self:
        """Get the step after this one in the normal flow of a game.

        Args:
            config: The config that sets the number of clue and discussion rounds.

        Returns:
            The next step. `DONE` and `ABORTED` are followed by themselves.
        """
        cls = type(self)

        match self.phase:
            case GamePhase.SETUP:
                return cls(phase=GamePhase.CLUE, round=1)
            case GamePhase.CLUE if (
                self.round is not None and self.round < config.clue_rounds
            ):
                return cls(phase=GamePhase.CLUE, round=self.round + 1)
            case GamePhase.CLUE if config.discussion_rounds > 0:
                return cls(phase=GamePhase.DISCUSSION, round=1)
            case GamePhase.DISCUSSION if (
                self.round is not None and self.round < config.discussion_rounds
            ):
                return cls(phase=GamePhase.DISCUSSION, round=self.round + 1)
            case GamePhase.CLUE | GamePhase.DISCUSSION:
                return cls(phase=GamePhase.VOTE)
            case GamePhase.VOTE:
                return cls(phase=GamePhase.RESOLUTION)
            case GamePhase.RESOLUTION:
                return cls(phase=GamePhase.GUESS)
            case GamePhase.GUESS:
                return cls(phase=GamePhase.OUTCOME)
            case GamePhase.OUTCOME:
                return cls(phase=GamePhase.DEBRIEF)
            case GamePhase.DEBRIEF:
                return cls(phase=GamePhase.DONE)
            case GamePhase.DONE | GamePhase.ABORTED:
                return self
