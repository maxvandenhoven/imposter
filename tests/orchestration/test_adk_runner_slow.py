"""A real game against Vertex AI. Run with `make test-slow`, which loads `.env`."""

import os

import pytest

from imposter.config import GameConfig, GamePhase
from imposter.engine.events import PlayerErrorEvent, ReflectionEvent
from imposter.orchestration.adk_runner import run_game
from imposter.orchestration.setup import GameRequest, GameSetup
from imposter.ports.event_bus import InMemoryEventBus
from imposter.ports.game_store import InMemoryGameStore
from imposter.words.options import WordMode, WordOptions

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("GOOGLE_CLOUD_PROJECT"), reason="needs GOOGLE_CLOUD_PROJECT"
    ),
]


async def test_short_game_with_real_models_reaches_the_end() -> None:
    setup = GameSetup.load(seed=7)
    config = GameConfig(
        players=setup.player_configs(["gemini-flash-lite"] * 3),
        clue_rounds=1,
        discussion_rounds=1,
        seed=7,
    )
    request = GameRequest(
        config=config, words=WordOptions(mode=WordMode.TYPED, word="lighthouse")
    )
    bus = InMemoryEventBus()

    game = await run_game(
        request=request, setup=setup, bus=bus, store=InMemoryGameStore()
    )
    published = [event async for event in bus.subscribe(game_id=game.game_id)]
    model_errors = [
        event.message
        for event in game.events_of_type(PlayerErrorEvent)
        if event.message.startswith(("no valid answer", "player failed"))
    ]

    assert game.phase is GamePhase.DONE
    assert published == list(game.events)
    assert model_errors == []
    assert len(game.events_of_type(ReflectionEvent)) == 3
    assert game.tokens_used > 0
