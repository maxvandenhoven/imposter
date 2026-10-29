from imposter.config import GamePhase
from imposter.engine.events import (
    GAME_EVENT_ADAPTER,
    ClueGivenEvent,
    EventVisibility,
    VoteCastEvent,
    public_projection,
)


def clue_event(*, clue: str | None) -> ClueGivenEvent:
    """Build a clue event with private reasoning."""
    return ClueGivenEvent(
        game_id="game",
        seq=3,
        phase=GamePhase.CLUE,
        round=1,
        seat=0,
        clue=clue,
        private_reasoning="secret plan",
    )


def test_public_projection_drops_private_fields() -> None:
    projection = public_projection(clue_event(clue="stripes"))

    assert projection is not None
    assert projection["clue"] == "stripes"
    assert projection["type"] == "clue_given"
    assert not ClueGivenEvent.private_fields & projection.keys()


def test_private_events_have_no_public_projection() -> None:
    event = VoteCastEvent(
        game_id="game",
        seq=1,
        phase=GamePhase.VOTE,
        seat=0,
        target=1,
        private_reasoning="",
    )

    assert event.visibility is EventVisibility.PRIVATE
    assert public_projection(event) is None


def test_events_round_trip_through_the_discriminated_union() -> None:
    event = clue_event(clue=None)

    assert GAME_EVENT_ADAPTER.validate_json(event.model_dump_json()) == event
