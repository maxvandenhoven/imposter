"""Real games against Vertex AI. Run with `make test-slow`, which loads `.env`."""

import os

import pytest

from imposter.config import GameConfig, GamePhase, PlayerConfig, SecretWord
from imposter.engine.events import (
    ClueGivenEvent,
    GuessMadeEvent,
    PlayerErrorEvent,
    ReflectionEvent,
    StatementMadeEvent,
    VoteCastEvent,
)
from imposter.engine.game import Game
from imposter.models.catalog import ModelCatalog
from imposter.orchestration.runner import GameRunner
from imposter.players.adk_player import AdkPlayer

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("GOOGLE_CLOUD_PROJECT"), reason="needs GOOGLE_CLOUD_PROJECT"
    ),
]


@pytest.mark.parametrize("model_id", ["gemini-flash-lite", "claude-haiku", "gpt-oss"])
async def test_real_model_gives_valid_responses_in_every_phase(model_id: str) -> None:
    entry = ModelCatalog.load().entry(model_id)
    config = GameConfig(
        players=[PlayerConfig(model_id=model_id)] * 3,
        clue_rounds=1,
        discussion_rounds=1,
        seed=7,
    )
    game = Game.create(
        config=config, secret=SecretWord(word="giraffe", category="animals")
    )
    players = [AdkPlayer(entry=entry, seat=seat.seat) for seat in game.seats]

    await GameRunner(players=players).play(game)

    model_errors = [
        event.message
        for event in game.events_of_type(PlayerErrorEvent)
        if event.message.startswith(("model call failed", "invalid answer", "player"))
    ]
    assert model_errors == []
    assert game.phase is GamePhase.DONE
    assert any(event.clue for event in game.events_of_type(ClueGivenEvent))
    assert all(event.statement for event in game.events_of_type(StatementMadeEvent))
    assert any(event.target is not None for event in game.events_of_type(VoteCastEvent))
    assert all(event.guess for event in game.events_of_type(GuessMadeEvent))
    assert all(event.reflection for event in game.events_of_type(ReflectionEvent))
    assert game.tokens_used > 0
