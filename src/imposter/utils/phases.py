from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from imposter.config import GameConfig, GamePhase

SEQUENTIAL_PHASES = frozenset({GamePhase.CLUE, GamePhase.DISCUSSION, GamePhase.GUESS})
"""Phases in which players act one at a time, in seat order."""

PARALLEL_PHASES = frozenset({GamePhase.VOTE, GamePhase.DEBRIEF})
"""Phases in which players act simultaneously, without seeing each other's action."""

ACTING_PHASES = SEQUENTIAL_PHASES | PARALLEL_PHASES
"""Phases in which players act. The other phases are played by the engine at once."""

ROUND_PHASES = frozenset({GamePhase.CLUE, GamePhase.DISCUSSION})
"""Phases that are played for a configured number of rounds."""

TERMINAL_PHASES = frozenset({GamePhase.DONE, GamePhase.ABORTED})
"""Phases after which nothing happens anymore."""


class PhaseTransitionReason(StrEnum):
    """Why a game moves from one phase to another."""

    NEXT_ROUND = "next_round"
    PHASE_DONE = "phase_done"
    NO_DISCUSSION = "no_discussion"
    SECRET_WORD_SAID = "secret_word_said"
    ABORTED = "aborted"


class PhaseTransition(BaseModel):
    """A move from one phase to another that a game can make.

    Attributes:
        source: The phase the game leaves.
        target: The phase the game enters, the same phase for the next round.
        reason: Why the game makes the move.
    """

    model_config = ConfigDict(frozen=True)

    source: GamePhase
    target: GamePhase
    reason: PhaseTransitionReason


PHASE_TRANSITIONS = (
    *(
        PhaseTransition(
            source=phase, target=phase, reason=PhaseTransitionReason.NEXT_ROUND
        )
        for phase in (GamePhase.CLUE, GamePhase.DISCUSSION)
    ),
    *(
        PhaseTransition(
            source=source, target=target, reason=PhaseTransitionReason.PHASE_DONE
        )
        for source, target in (
            (GamePhase.SETUP, GamePhase.CLUE),
            (GamePhase.CLUE, GamePhase.DISCUSSION),
            (GamePhase.DISCUSSION, GamePhase.VOTE),
            (GamePhase.VOTE, GamePhase.RESOLUTION),
            (GamePhase.RESOLUTION, GamePhase.GUESS),
            (GamePhase.GUESS, GamePhase.OUTCOME),
            (GamePhase.OUTCOME, GamePhase.DEBRIEF),
            (GamePhase.DEBRIEF, GamePhase.DONE),
        )
    ),
    PhaseTransition(
        source=GamePhase.CLUE,
        target=GamePhase.VOTE,
        reason=PhaseTransitionReason.NO_DISCUSSION,
    ),
    *(
        PhaseTransition(
            source=phase,
            target=GamePhase.OUTCOME,
            reason=PhaseTransitionReason.SECRET_WORD_SAID,
        )
        for phase in (GamePhase.CLUE, GamePhase.DISCUSSION)
    ),
    *(
        PhaseTransition(
            source=phase, target=GamePhase.ABORTED, reason=PhaseTransitionReason.ABORTED
        )
        for phase in sorted(ACTING_PHASES, key=list(GamePhase).index)
    ),
)
"""Every move between phases a game can make, the single source of the phase flow.

`next_phase` and the secret word exit look their target up here, and the ADK workflow
draws one edge per transition. A game is aborted from a phase in which players act,
because the other phases are played by the engine without waiting for anything.
"""


def transition_target(*, source: GamePhase, reason: PhaseTransitionReason) -> GamePhase:
    """Look up the phase a game moves to from a phase for a reason.

    Args:
        source: The phase the game leaves.
        reason: Why the game moves.

    Returns:
        The phase the game enters.

    Raises:
        ValueError: When the game cannot leave the phase for that reason.
    """
    for transition in PHASE_TRANSITIONS:
        if transition.source is source and transition.reason is reason:
            return transition.target

    message = f"A game cannot leave phase {source} because of {reason}."
    raise ValueError(message)


def phase_rounds(*, phase: GamePhase, config: GameConfig) -> int | None:
    """Get the number of rounds of a phase.

    Args:
        phase: The phase.
        config: The config that sets the number of clue and discussion rounds.

    Returns:
        The number of rounds, or `None` for a phase without rounds.
    """
    match phase:
        case GamePhase.CLUE:
            return config.clue_rounds
        case GamePhase.DISCUSSION:
            return config.discussion_rounds
        case _:
            return None


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
    if phase in TERMINAL_PHASES:
        return phase, None

    rounds = phase_rounds(phase=phase, config=config)

    if round_ is not None and rounds is not None and round_ < rounds:
        target = transition_target(source=phase, reason=PhaseTransitionReason.NEXT_ROUND)

        return target, round_ + 1

    target = transition_target(source=phase, reason=PhaseTransitionReason.PHASE_DONE)

    if target is GamePhase.DISCUSSION and config.discussion_rounds == 0:
        target = transition_target(
            source=phase, reason=PhaseTransitionReason.NO_DISCUSSION
        )

    return target, 1 if target in ROUND_PHASES else None
