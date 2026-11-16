"""A real game against Vertex AI. Run with `make test-slow`, which loads `.env`."""

import os

import pytest

from imposter.config import GameConfig, GamePhase
from imposter.engine.events import PlayerErrorEvent, ReflectionEvent, UsageEvent
from imposter.models.catalog import ModelCatalog
from imposter.orchestration.play import game_app, play_game
from imposter.orchestration.setup import GameRequest
from imposter.orchestration.workflow import GameWorkflowBuilder
from imposter.words.options import WordMode, WordOptions

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("GOOGLE_CLOUD_PROJECT"), reason="needs GOOGLE_CLOUD_PROJECT"
    ),
]


async def test_short_game_with_real_models_reaches_the_end() -> None:
    config = GameConfig(
        players=ModelCatalog.load().player_configs(["gemini-flash-lite"] * 3),
        clue_rounds=1,
        discussion_rounds=1,
        seed=7,
    )
    request = GameRequest(
        config=config, words=WordOptions(mode=WordMode.TYPED, word="lighthouse")
    )
    app = game_app(workflow=GameWorkflowBuilder.load(seed=7).build())

    events = [event async for event in play_game(app=app, request=request)]

    model_errors = [
        event.message
        for event in events
        if isinstance(event, PlayerErrorEvent)
        and event.message.startswith("player failed")
    ]
    assert events[-1].phase is GamePhase.DONE
    assert [event.seq for event in events] == list(range(len(events)))
    assert model_errors == []
    assert len([event for event in events if isinstance(event, ReflectionEvent)]) == 3
    assert any(isinstance(event, UsageEvent) for event in events)
