import random

import pytest
from pydantic import ValidationError

from imposter.engine.config import GameConfig, IdentityMode, PlayerConfig, WordMode
from imposter.engine.rules import NEUTRAL_NAMES


def players(count: int) -> list[PlayerConfig]:
    """Build `count` seats of the same model."""
    return [PlayerConfig(model_id="model")] * count


def test_defaults_match_the_game_rules() -> None:
    config = GameConfig(category="animals", players=players(4))

    assert config.word_mode is WordMode.RANDOM
    assert config.imposter_count == 1
    assert config.identity_mode is IdentityMode.NAMES
    assert config.public_category
    assert not config.imposter_hint
    assert (config.clue_rounds, config.discussion_rounds) == (2, 2)
    assert (config.statement_word_cap, config.reasoning_word_cap) == (100, 60)
    assert config.token_budget == 200_000


@pytest.mark.parametrize("count", [2, 9])
def test_player_count_is_bounded(count: int) -> None:
    with pytest.raises(ValidationError):
        GameConfig(category="animals", players=players(count))


@pytest.mark.parametrize(("count", "max_imposters"), [(3, 1), (4, 1), (5, 2), (8, 3)])
def test_imposter_count_is_at_most_half_of_the_others(
    count: int, max_imposters: int
) -> None:
    config = GameConfig(category="animals", players=players(count))

    assert config.max_imposters == max_imposters

    with pytest.raises(ValidationError, match="imposters"):
        GameConfig(
            category="animals", players=players(count), imposter_count=max_imposters + 1
        )


@pytest.mark.parametrize(
    ("fields", "match"),
    [
        ({"clue_rounds": 0}, "clue_rounds"),
        ({"clue_rounds": 4}, "clue_rounds"),
        ({"discussion_rounds": 4}, "discussion_rounds"),
        ({"word_mode": WordMode.TYPED}, "requires a word"),
        ({"category": None}, "requires a category"),
    ],
)
def test_invalid_options_are_rejected(fields: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        GameConfig.model_validate(
            {"category": "animals", "players": players(3), **fields}
        )


def test_generated_word_mode_needs_neither_word_nor_category() -> None:
    config = GameConfig(word_mode=WordMode.GENERATED, players=players(3))

    assert config.word is None


def test_seat_mode_numbers_players() -> None:
    names = IdentityMode.SEAT.seat_names(players=players(3), rng=random.Random(0))

    assert names == ["Player 1", "Player 2", "Player 3"]


def test_names_mode_picks_distinct_neutral_names() -> None:
    names = IdentityMode.NAMES.seat_names(players=players(8), rng=random.Random(0))

    assert len(set(names)) == 8
    assert set(names) <= set(NEUTRAL_NAMES)


def test_models_mode_numbers_repeated_models_only() -> None:
    lineup = [
        PlayerConfig(model_id="claude-sonnet", model_display_name="Claude Sonnet"),
        PlayerConfig(model_id="gemini-pro"),
        PlayerConfig(model_id="claude-sonnet", model_display_name="Claude Sonnet"),
    ]

    names = IdentityMode.MODELS.seat_names(players=lineup, rng=random.Random(0))

    assert names == ["Claude Sonnet #1", "gemini-pro", "Claude Sonnet #2"]
