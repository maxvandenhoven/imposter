"""Tests of `GameRunnerAgent`, kept to compare its games with the game workflow."""

import pytest
from conftest import FakeGameSetup
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from imposter.config import GameConfig, GamePhase, PlayerConfig
from imposter.engine.events import GAME_EVENT_ADAPTER
from imposter.orchestration.runner_agent import REQUEST_STATE_KEY, GameRunnerAgent
from imposter.orchestration.setup import GameRequest
from imposter.ports.game_store import InMemoryGameStore

MODEL_IDS = ["gemini-flash", "claude-haiku", "gpt-oss", "gemini-flash-lite"]


def new_request(**options: object) -> GameRequest:
    """Build a seeded request for a four-seat game."""
    players = [PlayerConfig(model_id=model_id) for model_id in MODEL_IDS]
    config = GameConfig.model_validate({"players": players, "seed": 5, **options})

    return GameRequest(config=config)


async def run_session(
    agent: GameRunnerAgent, *, sessions: InMemorySessionService, state: dict
) -> list[str]:
    """Run the agent once in the session `game-1` and collect the text of its events."""
    runner = Runner(app_name="test", agent=agent, session_service=sessions)

    if await sessions.get_session(app_name="test", user_id="u", session_id="game-1"):
        session_id = "game-1"
    else:
        session = await sessions.create_session(
            app_name="test", user_id="u", session_id="game-1", state=state
        )
        session_id = session.id

    message = types.Content(role="user", parts=[types.Part(text="Play.")])

    return [
        part.text or ""
        async for event in runner.run_async(
            user_id="u", session_id=session_id, new_message=message
        )
        if event.content and event.content.parts
        for part in event.content.parts
    ]


async def test_agent_yields_every_engine_event_as_adk_event() -> None:
    store = InMemoryGameStore()
    agent = GameRunnerAgent(name="game_runner", setup=FakeGameSetup(), store=store)
    sessions = InMemorySessionService()
    state = {REQUEST_STATE_KEY: new_request().model_dump(mode="json")}

    texts = await run_session(agent, sessions=sessions, state=state)
    game = store.get("game-1")

    assert game is not None
    assert [GAME_EVENT_ADAPTER.validate_json(text) for text in texts] == list(game.events)

    again = await run_session(agent, sessions=sessions, state=state)

    assert again == ["Game game-1 was already played."]


async def test_agent_uses_the_default_request_without_one_in_state() -> None:
    store = InMemoryGameStore()
    agent = GameRunnerAgent(
        name="game_runner",
        setup=FakeGameSetup(),
        store=store,
        default_request=new_request(clue_rounds=1),
    )

    await run_session(agent, sessions=InMemorySessionService(), state={})
    game = store.get("game-1")

    assert game is not None
    assert game.config.clue_rounds == 1
    assert game.phase is GamePhase.DONE


async def test_agent_without_any_request_fails() -> None:
    agent = GameRunnerAgent(name="game_runner", setup=FakeGameSetup())

    with pytest.raises(ValueError, match="no game request"):
        await run_session(agent, sessions=InMemorySessionService(), state={})
