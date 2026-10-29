from imposter.config import GameConfig, GamePhase

SEQUENTIAL_PHASES = frozenset({GamePhase.CLUE, GamePhase.DISCUSSION, GamePhase.GUESS})
"""Phases in which players act one at a time, in seat order."""

PARALLEL_PHASES = frozenset({GamePhase.VOTE, GamePhase.DEBRIEF})
"""Phases in which players act simultaneously, without seeing each other's action."""

TERMINAL_PHASES = frozenset({GamePhase.DONE, GamePhase.ABORTED})
"""Phases after which nothing happens anymore."""


def next_phase(
    *, phase: GamePhase, round_: int | None, config: GameConfig
) -> tuple[GamePhase, int | None]:
    """Get the phase and round that follow a phase and round in the normal flow.

    Args:
        phase: The current phase.
        round_: The 1-based round of a clue or discussion phase, otherwise `None`.
        config: The config that sets the number of clue and discussion rounds.

    Returns:
        The next phase and its round. `DONE` and `ABORTED` are followed by themselves.
    """
    match phase:
        case GamePhase.SETUP:
            return GamePhase.CLUE, 1
        case GamePhase.CLUE if round_ is not None and round_ < config.clue_rounds:
            return GamePhase.CLUE, round_ + 1
        case GamePhase.CLUE if config.discussion_rounds > 0:
            return GamePhase.DISCUSSION, 1
        case GamePhase.DISCUSSION if (
            round_ is not None and round_ < config.discussion_rounds
        ):
            return GamePhase.DISCUSSION, round_ + 1
        case GamePhase.CLUE | GamePhase.DISCUSSION:
            return GamePhase.VOTE, None
        case GamePhase.VOTE:
            return GamePhase.RESOLUTION, None
        case GamePhase.RESOLUTION:
            return GamePhase.GUESS, None
        case GamePhase.GUESS:
            return GamePhase.OUTCOME, None
        case GamePhase.OUTCOME:
            return GamePhase.DEBRIEF, None
        case GamePhase.DEBRIEF:
            return GamePhase.DONE, None
        case GamePhase.DONE | GamePhase.ABORTED:
            return phase, None
