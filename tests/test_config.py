import pytest
from pydantic import ValidationError

from imposter.config import GameConfig, IdentityMode, PlayerConfig, max_imposters


def players(count: int) -> list[PlayerConfig]:
    """Build `count` seats of the same model."""
    return [PlayerConfig(model_id="model")] * count


def test_defaults_match_the_game_rules() -> None:
    config = GameConfig(players=players(4))

    assert config.imposter_count == 1
    assert config.identity_mode is IdentityMode.NAMES
    assert not config.public_category
    assert not config.imposter_hint
    assert (config.clue_rounds, config.discussion_rounds) == (2, 2)
    assert (config.statement_word_cap, config.reasoning_word_cap) == (100, 60)
    assert config.token_budget == 200_000


@pytest.mark.parametrize("count", [2, 9])
def test_player_count_is_bounded(count: int) -> None:
    with pytest.raises(ValidationError):
        GameConfig(players=players(count))


@pytest.mark.parametrize(("count", "allowed"), [(3, 1), (4, 1), (5, 2), (8, 3)])
def test_imposter_count_is_at_most_half_of_the_others(count: int, allowed: int) -> None:
    assert max_imposters(count) == allowed

    with pytest.raises(ValidationError, match="imposters"):
        GameConfig(players=players(count), imposter_count=allowed + 1)


@pytest.mark.parametrize(
    "fields", [{"clue_rounds": 0}, {"clue_rounds": 4}, {"discussion_rounds": 4}]
)
def test_round_counts_are_bounded(fields: dict[str, int]) -> None:
    with pytest.raises(ValidationError, match=next(iter(fields))):
        GameConfig.model_validate({"players": players(3), **fields})
