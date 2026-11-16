import pytest
from fakes import RANDOM_VOCABULARY, RandomPlayer, ScriptedPlayer

from imposter.config import GameConfig, PlayerConfig, SecretWord
from imposter.engine.game import Game
from imposter.engine.responses import ClueResponse
from imposter.engine.views import PlayerView


@pytest.fixture(scope="function")
def view() -> PlayerView:
    """Return the first view of seat 0 in a fresh game."""
    config = GameConfig(players=[PlayerConfig(model_id="m")] * 3, seed=1)
    game = Game.create(config=config, secret=SecretWord(word="giraffe"))

    return game.view_for(0)


def test_scripted_player_replays_steps_in_order(view: PlayerView) -> None:
    player = ScriptedPlayer(script=[ClueResponse(clue="a"), ClueResponse(clue="b")])

    first = player.respond(view)
    second = player.respond(view, "try again")

    assert (first, second) == (ClueResponse(clue="a"), ClueResponse(clue="b"))
    assert player.views == [view, view]
    assert player.retry_reasons == [None, "try again"]


def test_scripted_player_raises_error_steps_and_when_exhausted(view: PlayerView) -> None:
    player = ScriptedPlayer(script=[ValueError("boom")])

    with pytest.raises(ValueError, match="boom"):
        player.respond(view)

    with pytest.raises(LookupError, match="exhausted"):
        player.respond(view)


def test_random_player_gives_an_unused_clue_with_traceable_reasoning(
    view: PlayerView,
) -> None:
    response = RandomPlayer(seed=3).respond(view)

    assert isinstance(response, ClueResponse)
    assert response.clue in RANDOM_VOCABULARY
    assert response.private_reasoning.startswith("reasoning-seat0-turn1")
