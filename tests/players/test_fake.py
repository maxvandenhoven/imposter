import pytest

from imposter.config import GameConfig, PlayerConfig, SecretWord
from imposter.engine.game import Game
from imposter.engine.views import PlayerView
from imposter.players.base import ClueResponse, PlayerResponse, TurnUsage
from imposter.players.fake import RANDOM_VOCABULARY, RandomPlayer, ScriptedPlayer


@pytest.fixture(scope="function")
def view() -> PlayerView:
    """Return the first view of seat 0 in a fresh game."""
    config = GameConfig(players=[PlayerConfig(model_id="m")] * 3, seed=1)
    game = Game.create(config=config, secret=SecretWord(word="giraffe"))

    return game.view_for(0)


async def test_scripted_player_replays_steps_in_order(view: PlayerView) -> None:
    usage = TurnUsage(model_id="m", input_tokens=3)
    full = PlayerResponse(output=ClueResponse(clue="b"), error="bad json")
    player = ScriptedPlayer(script=[ClueResponse(clue="a"), full], usage=usage)

    first = await player.take_turn(view=view)
    second = await player.take_turn(view=view, retry_reason="try again")

    assert first == PlayerResponse(output=ClueResponse(clue="a"), usage=usage)
    assert second is full
    assert player.views == [view, view]
    assert player.retry_reasons == [None, "try again"]


async def test_scripted_player_raises_error_steps_and_when_exhausted(
    view: PlayerView,
) -> None:
    player = ScriptedPlayer(script=[ValueError("boom")])

    with pytest.raises(ValueError, match="boom"):
        await player.take_turn(view=view)

    with pytest.raises(LookupError, match="exhausted"):
        await player.take_turn(view=view)


async def test_random_player_gives_an_unused_clue_with_traceable_reasoning(
    view: PlayerView,
) -> None:
    response = await RandomPlayer(seed=3).take_turn(view=view)

    assert isinstance(response.output, ClueResponse)
    assert response.output.clue in RANDOM_VOCABULARY
    assert response.output.private_reasoning.startswith("reasoning-seat0-turn1")
