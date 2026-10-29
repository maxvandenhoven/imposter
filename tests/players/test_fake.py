import pytest

from imposter.engine.config import GameConfig, GamePhase, PlayerConfig, SecretWord
from imposter.engine.state import GameState
from imposter.engine.views import PlayerView
from imposter.players.base import ClueResponse, PlayerResponse, PlayerTask, TurnUsage
from imposter.players.fake import RANDOM_VOCABULARY, RandomPlayer, ScriptedPlayer


@pytest.fixture(scope="function")
def view() -> PlayerView:
    """Return the first view of seat 0 in a fresh game."""
    config = GameConfig(
        category="animals", players=[PlayerConfig(model_id="m")] * 3, seed=1
    )
    state = GameState.create(config=config, secret=SecretWord(word="giraffe"))

    return state.view_for(0)


async def test_scripted_player_replays_steps_in_order(view: PlayerView) -> None:
    usage = TurnUsage(model_id="m", input_tokens=3)
    full = PlayerResponse(output=ClueResponse(clue="b"), attempts=2)
    player = ScriptedPlayer(seat=0, script=[ClueResponse(clue="a"), full], usage=usage)
    task = PlayerTask.for_view(view)

    first = await player.take_turn(view=view, task=task)
    second = await player.take_turn(view=view, task=task)

    assert first == PlayerResponse(output=ClueResponse(clue="a"), usage=usage)
    assert second is full
    assert player.views == [view, view]
    assert player.tasks == [task, task]


async def test_scripted_player_raises_error_steps_and_when_exhausted(
    view: PlayerView,
) -> None:
    player = ScriptedPlayer(seat=0, script=[ValueError("boom")])
    task = PlayerTask.for_view(view)

    with pytest.raises(ValueError, match="boom"):
        await player.take_turn(view=view, task=task)

    with pytest.raises(LookupError, match="exhausted"):
        await player.take_turn(view=view, task=task)


async def test_random_player_gives_an_unused_clue_with_traceable_reasoning(
    view: PlayerView,
) -> None:
    player = RandomPlayer(seat=0, seed=3)

    response = await player.take_turn(view=view, task=PlayerTask.for_view(view))

    assert isinstance(response.output, ClueResponse)
    assert response.output.clue in RANDOM_VOCABULARY
    assert response.output.private_reasoning.startswith("reasoning-seat0-turn1")


def test_player_task_takes_phase_and_limits_from_the_view(view: PlayerView) -> None:
    task = PlayerTask.for_view(view, retry_reason="try again")

    assert task.phase is GamePhase.CLUE
    assert task.round == 1
    assert task.statement_word_cap == view.rules.statement_word_cap
    assert task.retry_reason == "try again"
    assert task.response_type is ClueResponse
