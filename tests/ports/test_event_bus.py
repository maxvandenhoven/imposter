import asyncio

import pytest

from imposter.config import GamePhase
from imposter.engine.events import BaseGameEvent, PhaseStartedEvent
from imposter.ports.event_bus import InMemoryEventBus

GAME_ID = "game-1"


def phase_event(seq: int) -> PhaseStartedEvent:
    """Build a `phase_started` event with a given `seq`."""
    return PhaseStartedEvent(game_id=GAME_ID, seq=seq, phase=GamePhase.CLUE, round=1)


async def collect(bus: InMemoryEventBus, from_seq: int = 0) -> list[int]:
    """Subscribe to the game and collect the `seq` of every event until the end."""
    return [
        event.seq async for event in bus.subscribe(game_id=GAME_ID, from_seq=from_seq)
    ]


async def test_subscribe_replays_from_seq_then_tails_until_closed() -> None:
    bus = InMemoryEventBus()

    for seq in range(3):
        bus.publish(game_id=GAME_ID, event=phase_event(seq))

    subscriber = asyncio.create_task(collect(bus, from_seq=1))
    await asyncio.sleep(0)
    bus.publish(game_id=GAME_ID, event=phase_event(3))
    await asyncio.sleep(0)
    bus.publish(game_id=GAME_ID, event=phase_event(4))
    bus.close(GAME_ID)

    assert await subscriber == [1, 2, 3, 4]


async def test_subscribers_before_the_first_event_and_after_close_see_all() -> None:
    bus = InMemoryEventBus()
    early = asyncio.create_task(collect(bus))
    await asyncio.sleep(0)

    for seq in range(2):
        bus.publish(game_id=GAME_ID, event=phase_event(seq))

    bus.close(GAME_ID)

    assert await early == [0, 1]
    assert await collect(bus) == [0, 1]


async def test_streams_of_games_are_separate() -> None:
    bus = InMemoryEventBus()
    bus.publish(game_id="other", event=phase_event(0))
    bus.close(GAME_ID)

    events: list[BaseGameEvent] = [
        event async for event in bus.subscribe(game_id=GAME_ID)
    ]

    assert events == []


def test_publish_after_close_is_rejected() -> None:
    bus = InMemoryEventBus()
    bus.close(GAME_ID)

    with pytest.raises(ValueError, match="closed"):
        bus.publish(game_id=GAME_ID, event=phase_event(0))
