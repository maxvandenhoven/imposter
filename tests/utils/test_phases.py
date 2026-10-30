import itertools

import pytest

from imposter.config import GameConfig, GamePhase, PlayerConfig
from imposter.utils.phases import (
    ACTING_PHASES,
    PHASE_TRANSITIONS,
    TERMINAL_PHASES,
    PhaseTransitionReason,
    next_phase,
    transition_target,
)


def flow(config: GameConfig) -> list[tuple[GamePhase, int | None]]:
    """List every phase and round from setup to done."""
    steps: list[tuple[GamePhase, int | None]] = [(GamePhase.SETUP, None)]

    while steps[-1][0] not in TERMINAL_PHASES:
        phase, round_ = steps[-1]
        steps.append(next_phase(phase=phase, round_=round_, config=config))

    return steps


def config_with(*, clue_rounds: int, discussion_rounds: int) -> GameConfig:
    """Build a config with the given numbers of rounds."""
    return GameConfig(
        players=[PlayerConfig(model_id="model")] * 3,
        clue_rounds=clue_rounds,
        discussion_rounds=discussion_rounds,
    )


def test_default_flow_has_two_clue_and_two_discussion_rounds() -> None:
    assert flow(config_with(clue_rounds=2, discussion_rounds=2)) == [
        (GamePhase.SETUP, None),
        (GamePhase.CLUE, 1),
        (GamePhase.CLUE, 2),
        (GamePhase.DISCUSSION, 1),
        (GamePhase.DISCUSSION, 2),
        (GamePhase.VOTE, None),
        (GamePhase.RESOLUTION, None),
        (GamePhase.GUESS, None),
        (GamePhase.OUTCOME, None),
        (GamePhase.DEBRIEF, None),
        (GamePhase.DONE, None),
    ]


def test_flow_without_discussion_goes_from_clues_to_vote() -> None:
    assert flow(config_with(clue_rounds=1, discussion_rounds=0))[:3] == [
        (GamePhase.SETUP, None),
        (GamePhase.CLUE, 1),
        (GamePhase.VOTE, None),
    ]


def test_terminal_phases_follow_themselves() -> None:
    config = config_with(clue_rounds=1, discussion_rounds=0)

    for phase in TERMINAL_PHASES:
        assert next_phase(phase=phase, round_=None, config=config) == (phase, None)


def reference_next_phase(
    *, phase: GamePhase, round_: int | None, config: GameConfig
) -> tuple[GamePhase, int | None]:
    """The `next_phase` from before the transition table, to compare against."""
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
        case _:
            return phase, None


@pytest.mark.parametrize("clue_rounds", [1, 2, 3])
@pytest.mark.parametrize("discussion_rounds", [0, 1, 2, 3])
@pytest.mark.parametrize("phase", list(GamePhase))
@pytest.mark.parametrize("round_", [None, 1, 2, 3])
def test_next_phase_behaves_as_before_the_transition_table(
    clue_rounds: int, discussion_rounds: int, phase: GamePhase, round_: int | None
) -> None:
    config = config_with(clue_rounds=clue_rounds, discussion_rounds=discussion_rounds)

    assert next_phase(phase=phase, round_=round_, config=config) == (
        reference_next_phase(phase=phase, round_=round_, config=config)
    )


@pytest.mark.parametrize("clue_rounds", [1, 2, 3])
@pytest.mark.parametrize("discussion_rounds", [0, 1, 2, 3])
def test_every_step_of_the_flow_is_a_transition(
    clue_rounds: int, discussion_rounds: int
) -> None:
    steps = flow(
        config_with(clue_rounds=clue_rounds, discussion_rounds=discussion_rounds)
    )
    edges = {(transition.source, transition.target) for transition in PHASE_TRANSITIONS}

    for (source, _), (target, _) in itertools.pairwise(steps):
        assert (source, target) in edges


def test_transitions_are_unique() -> None:
    keys = [(transition.source, transition.reason) for transition in PHASE_TRANSITIONS]

    assert len(keys) == len(set(keys))


def test_players_can_be_aborted_in_every_acting_phase() -> None:
    for phase in ACTING_PHASES:
        target = transition_target(source=phase, reason=PhaseTransitionReason.ABORTED)

        assert target is GamePhase.ABORTED


def test_secret_word_exit_goes_to_outcome() -> None:
    for phase in (GamePhase.CLUE, GamePhase.DISCUSSION):
        target = transition_target(
            source=phase, reason=PhaseTransitionReason.SECRET_WORD_SAID
        )

        assert target is GamePhase.OUTCOME


def test_unknown_transition_is_an_error() -> None:
    with pytest.raises(ValueError, match="cannot leave phase vote"):
        transition_target(
            source=GamePhase.VOTE, reason=PhaseTransitionReason.SECRET_WORD_SAID
        )
