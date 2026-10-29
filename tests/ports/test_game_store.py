from imposter.config import GameConfig, PlayerConfig, SecretWord
from imposter.engine.game import Game
from imposter.ports.game_store import InMemoryGameStore


def new_game(game_id: str) -> Game:
    """Create a three-seat game with a given id."""
    config = GameConfig(players=[PlayerConfig(model_id="fake")] * 3)

    return Game.create(config=config, secret=SecretWord(word="giraffe"), game_id=game_id)


def test_store_gets_saved_games_and_lists_the_newest_first() -> None:
    store = InMemoryGameStore()
    first, second = new_game("first"), new_game("second")
    store.save(first)
    store.save(second)

    assert store.get("first") is first
    assert store.get("missing") is None
    assert store.list_recent() == [second, first]
    assert store.list_recent(limit=1) == [second]
