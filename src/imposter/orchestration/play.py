from collections.abc import AsyncGenerator

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.apps import App
from google.adk.plugins import BasePlugin
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import Workflow
from google.genai import types

from imposter.engine.events import GAME_EVENT_ADAPTER, GameEvent
from imposter.orchestration.setup import GameRequest
from imposter.orchestration.workflow import GAME_EVENT_METADATA_KEY, REQUEST_STATE_KEY

APP_NAME = "imposter"
"""The ADK app name of the game."""

USER_ID = "imposter"
"""The ADK user of game sessions that no web user started."""

START_MESSAGE = "Play the game."
"""The user message that starts a game run."""


def game_app(*, workflow: Workflow, plugins: list[BasePlugin] | None = None) -> App:
    """Build the ADK app of the game.

    Args:
        workflow: The game workflow.
        plugins: The plugins of the app, such as the one that traces games.

    Returns:
        The app, for ADK's `Runner`, its API server and `adk web`.
    """
    return App(name=APP_NAME, root_agent=workflow, plugins=plugins or [])


async def play_game(
    *, app: App, request: GameRequest, game_id: str | None = None
) -> AsyncGenerator[GameEvent]:
    """Play one game with ADK's `Runner`, in a new in-memory session.

    This is what a client of the API does over HTTP: it puts the request in the initial
    state of a session, runs the session and reads the engine events from the custom
    metadata of the ADK events.

    Args:
        app: The app of the game.
        request: The options and how to choose the word.
        game_id: The id of the game and of its session, a random id when not given.

    Yields:
        The engine events of the game, as they happen.
    """
    runner = Runner(app=app, session_service=InMemorySessionService())
    session = await runner.session_service.create_session(
        app_name=app.name,
        user_id=USER_ID,
        session_id=game_id,
        state={REQUEST_STATE_KEY: request.model_dump(mode="json")},
    )
    start = types.Content(role="user", parts=[types.Part(text=START_MESSAGE)])

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=start,
        run_config=RunConfig(streaming_mode=StreamingMode.NONE),
    ):
        game_event = (event.custom_metadata or {}).get(GAME_EVENT_METADATA_KEY)

        if game_event is not None:
            yield GAME_EVENT_ADAPTER.validate_python(game_event)
