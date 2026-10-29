from imposter.config import MAX_PLAYERS, IdentityMode, PlayerConfig
from imposter.utils.names import seat_names


def players(count: int) -> list[PlayerConfig]:
    """Build `count` seats of the same model."""
    return [PlayerConfig(model_id="model")] * count


def test_seat_mode_numbers_players() -> None:
    names = seat_names(mode=IdentityMode.SEAT, players=players(3))

    assert names == ["Player 1", "Player 2", "Player 3"]


def test_names_mode_gives_classic_names_in_alphabetical_order() -> None:
    assert seat_names(mode=IdentityMode.NAMES, players=players(4)) == [
        "Alice",
        "Bob",
        "Charlie",
        "Dave",
    ]


def test_names_mode_has_a_name_for_every_seat() -> None:
    names = seat_names(mode=IdentityMode.NAMES, players=players(MAX_PLAYERS))

    assert len(set(names)) == MAX_PLAYERS
    assert names == sorted(names)


def test_models_mode_numbers_repeated_models_only() -> None:
    lineup = [
        PlayerConfig(model_id="claude-sonnet", model_display_name="Claude Sonnet"),
        PlayerConfig(model_id="gemini-pro"),
        PlayerConfig(model_id="claude-sonnet", model_display_name="Claude Sonnet"),
    ]

    names = seat_names(mode=IdentityMode.MODELS, players=lineup)

    assert names == ["Claude Sonnet #1", "gemini-pro", "Claude Sonnet #2"]
