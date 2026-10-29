import uuid

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from imposter.engine.game import Game
from imposter.orchestration.runner_agent import REQUEST_STATE_KEY, GameRunnerAgent
from imposter.orchestration.setup import GameRequest, GameSetup
from imposter.ports.event_bus import EventBusProtocol
from imposter.ports.game_store import GameStoreProtocol

APP_NAME = "imposter"
"""The ADK app name of the game runner."""

USER_ID = "imposter"
"""The ADK user of the game sessions."""

AGENT_NAME = "game_runner"
"""The ADK name of the `GameRunnerAgent`."""

START_MESSAGE = "Play the game."
"""The user message that starts a game run."""


async def run_game(
    *,
    request: GameRequest,
    setup: GameSetup,
    bus: EventBusProtocol,
    store: GameStoreProtocol,
    game_id: str | None = None,
) -> Game:
    """Play one game with ADK's `Runner`, in a session whose id is the game id.

    The request goes into the initial session state, where the `GameRunnerAgent` reads
    it. Subscribe to the bus with the game id to follow the game while it runs.

    Args:
        request: The options and how to choose the word.
        setup: Creates the game and seats its players.
        bus: Carries the engine events to subscribers.
        store: Keeps the game.
        game_id: The id of the game, a random id when not given.

    Returns:
        The game, done or aborted.

    Raises:
        RuntimeError: When the agent did not create the game.
    """
    sessions = InMemorySessionService()
    agent = GameRunnerAgent(
        name=AGENT_NAME,
        description="Plays a game of Imposter between LLM players.",
        setup=setup,
        bus=bus,
        store=store,
    )
    runner = Runner(app_name=APP_NAME, agent=agent, session_service=sessions)
    session = await sessions.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=game_id or uuid.uuid4().hex,
        state={REQUEST_STATE_KEY: request.model_dump(mode="json")},
    )
    start = types.Content(role="user", parts=[types.Part(text=START_MESSAGE)])

    async for _ in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=start
    ):
        pass

    game = store.get(session.id)

    if game is None:
        message = f"The game runner did not create game {session.id}."
        raise RuntimeError(message)

    return game
