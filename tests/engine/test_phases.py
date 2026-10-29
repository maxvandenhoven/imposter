from imposter.engine.config import GameConfig, GamePhase, PlayerConfig
from imposter.engine.phases import PhaseStep


def flow(config: GameConfig) -> list[tuple[GamePhase, int | None]]:
    """List every step from setup to done."""
    step = PhaseStep(phase=GamePhase.SETUP)
    steps = [(step.phase, step.round)]

    while not step.is_terminal:
        step = step.following(config)
        steps.append((step.phase, step.round))

    return steps


def config_with(*, clue_rounds: int, discussion_rounds: int) -> GameConfig:
    """Build a config with the given numbers of rounds."""
    return GameConfig(
        category="animals",
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


def test_terminal_steps_follow_themselves() -> None:
    config = config_with(clue_rounds=1, discussion_rounds=0)
    aborted = PhaseStep(phase=GamePhase.ABORTED)

    assert aborted.following(config) == aborted
    assert aborted.is_terminal
    assert not aborted.is_sequential
