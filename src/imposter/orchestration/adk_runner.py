import uuid

from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from imposter.engine.game import Game
from imposter.orchestration.runner_workflow import (
    REQUEST_STATE_KEY,
    GameSessions,
    game_workflow,
)
from imposter.orchestration.setup import GameRequest, GameSetup
from imposter.ports.event_bus import EventBusProtocol
from imposter.ports.game_store import GameStoreProtocol
from imposter.telemetry.spans import GameTracePlugin

APP_NAME = "imposter"
"""The ADK app name of the game runner."""

USER_ID = "imposter"
"""The ADK user of the game sessions."""

START_MESSAGE = "Play the game."
"""The user message that starts a game run."""


async def run_game(
    *,
    request: GameRequest,
    setup: GameSetup,
    bus: EventBusProtocol,
    store: GameStoreProtocol,
    game_id: str | None = None,
    trace_plugin: GameTracePlugin | None = None,
) -> Game:
    """Play one game with ADK's `Runner` and the game workflow, in a session per game.

    The session id is the game id. The request goes into the initial session state,
    where the setup node of the workflow reads it. Subscribe to the bus with the game id
    to follow the game while it runs. When the run stops early, for example because its
    task was cancelled, the game is aborted and the bus closed. The trace plugin puts
    the game attributes on the root span of the run and notes its trace id.

    Args:
        request: The options and how to choose the word.
        setup: Creates the game and seats its players.
        bus: Carries the engine events to subscribers.
        store: Keeps the game.
        game_id: The id of the game, a random id when not given.
        trace_plugin: Puts the game attributes on the trace, a new one when not given.

    Returns:
        The game, done or aborted.

    Raises:
        RuntimeError: When the workflow did not create the game.
    """
    sessions = GameSessions(setup=setup, bus=bus, store=store)
    session_service = InMemorySessionService()
    plugin = trace_plugin or GameTracePlugin(find_game=store.get, catalog=setup.catalog)
    app = App(
        name=APP_NAME, root_agent=game_workflow(sessions=sessions), plugins=[plugin]
    )
    runner = Runner(app=app, session_service=session_service)
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=game_id or uuid.uuid4().hex,
        state={REQUEST_STATE_KEY: request.model_dump(mode="json")},
    )
    start = types.Content(role="user", parts=[types.Part(text=START_MESSAGE)])

    try:
        async for _ in runner.run_async(
            user_id=USER_ID, session_id=session.id, new_message=start
        ):
            pass
    finally:
        sessions.finish(session.id)

    game = store.get(session.id)

    if game is None:
        message = f"The game workflow did not create game {session.id}."
        raise RuntimeError(message)

    return game
