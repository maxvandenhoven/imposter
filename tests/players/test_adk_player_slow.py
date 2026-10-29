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
from imposter.players.base import (
    ClueResponse,
    DebriefResponse,
    DiscussionResponse,
    PlayerProtocol,
    VoteResponse,
)
from imposter.players.fake import ScriptedPlayer

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("GOOGLE_CLOUD_PROJECT"), reason="needs GOOGLE_CLOUD_PROJECT"
    ),
]

VAGUE_CLUES = ("yellow", "patient")
"""Scripted civilian clues that do not give the word away, so the real imposter cannot
infer and say it, which would end the game before the vote and the guess."""


@pytest.mark.parametrize("model_id", ["gemini-flash-lite", "claude-haiku", "gpt-oss"])
async def test_real_model_gives_valid_responses_in_every_phase(model_id: str) -> None:
    """The real model plays the imposter, which acts in all five phases."""
    entry = ModelCatalog.load().entry(model_id)
    config = GameConfig(
        players=[PlayerConfig(model_id=model_id)] * 3,
        clue_rounds=1,
        discussion_rounds=1,
        seed=7,
    )
    game = Game.create(config=config, secret=SecretWord(word="giraffe"))
    imposter = game.imposters[0]
    civilians = [seat.seat for seat in game.seats if seat.seat != imposter]
    players: list[PlayerProtocol] = []

    for seat in game.seats:
        if seat.seat == imposter:
            players.append(AdkPlayer(entry=entry, seat=seat.seat))
            continue

        clue = VAGUE_CLUES[civilians.index(seat.seat)]
        script = [
            ClueResponse(clue=clue),
            DiscussionResponse(statement="I am not sure yet, the clues are vague."),
            VoteResponse(vote_for=game.seats[imposter].name),
            DebriefResponse(reflection="Good game."),
        ]
        players.append(ScriptedPlayer(script=script))

    await GameRunner(players=players).play(game)

    def of_imposter[EventT](events: list[EventT]) -> list[EventT]:
        return [event for event in events if getattr(event, "seat", None) == imposter]

    model_errors = [
        event.message
        for event in game.events_of_type(PlayerErrorEvent)
        if event.message.startswith(("no valid answer", "player failed"))
    ]
    assert model_errors == []
    assert game.phase is GamePhase.DONE
    assert of_imposter(game.events_of_type(ClueGivenEvent))[0].clue
    assert of_imposter(game.events_of_type(StatementMadeEvent))[0].statement
    assert of_imposter(game.events_of_type(VoteCastEvent))[0].target is not None
    assert of_imposter(game.events_of_type(GuessMadeEvent))[0].guess
    assert of_imposter(game.events_of_type(ReflectionEvent))[0].reflection
    assert game.tokens_used > 0
