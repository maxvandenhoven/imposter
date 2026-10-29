from imposter.engine.config import GamePhase, PlayerRole
from imposter.engine.events import (
    GAME_EVENT_ADAPTER,
    ClueGivenEvent,
    EventVisibility,
    RoleAssignedEvent,
)


def test_public_projection_drops_private_fields() -> None:
    event = ClueGivenEvent(
        game_id="game",
        seq=3,
        phase=GamePhase.CLUE,
        round=1,
        seat=0,
        clue="stripes",
        private_reasoning="secret plan",
    )

    projection = event.public_projection()

    assert projection is not None
    assert projection["clue"] == "stripes"
    assert projection["type"] == "clue_given"
    assert not ClueGivenEvent.private_fields & projection.keys()


def test_private_events_have_no_public_projection() -> None:
    event = RoleAssignedEvent(
        game_id="game", seq=1, phase=GamePhase.SETUP, seat=0, role=PlayerRole.IMPOSTER
    )

    assert event.visibility is EventVisibility.PRIVATE
    assert event.public_projection() is None


def test_events_round_trip_through_the_discriminated_union() -> None:
    event = ClueGivenEvent(
        game_id="game",
        seq=3,
        phase=GamePhase.CLUE,
        round=1,
        seat=0,
        clue=None,
        private_reasoning="",
    )

    parsed = GAME_EVENT_ADAPTER.validate_json(event.model_dump_json())

    assert parsed == event
