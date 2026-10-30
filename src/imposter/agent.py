"""The game workflow as the ADK `app` that `adk web src` loads, one game per session.

The app carries the plugin that puts the game attributes on the root span of a game.
"""

from google.adk.apps import App

from imposter.config import GameConfig
from imposter.orchestration.adk_runner import APP_NAME
from imposter.orchestration.runner_workflow import GameSessions, game_workflow
from imposter.orchestration.setup import DEFAULT_MODEL_IDS, GameRequest, GameSetup
from imposter.ports.event_bus import InMemoryEventBus
from imposter.ports.game_store import InMemoryGameStore
from imposter.telemetry.spans import GameTracePlugin

setup = GameSetup.load()
store = InMemoryGameStore()

root_agent = game_workflow(
    sessions=GameSessions(
        setup=setup,
        bus=InMemoryEventBus(),
        store=store,
        default_request=GameRequest(
            config=GameConfig(players=setup.player_configs(DEFAULT_MODEL_IDS))
        ),
    )
)

app = App(
    name=APP_NAME, root_agent=root_agent, plugins=[GameTracePlugin(find_game=store.get)]
)
