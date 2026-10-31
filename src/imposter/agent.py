"""The game workflow as the ADK `app` of `adk web src` and the API, one game per session.

The app carries the plugin that puts the game attributes on the root span of a game
and notes the trace id of each game, which the API links to.
`adk web --otel_to_cloud` exports the traces, and the telemetry defaults make ADK log
the prompts and completions, as the CLI does.
"""

from google.adk.apps import App

from imposter.config import GameConfig
from imposter.orchestration.adk_runner import APP_NAME
from imposter.orchestration.runner_workflow import GameSessions, game_workflow
from imposter.orchestration.setup import DEFAULT_MODEL_IDS, GameRequest, GameSetup
from imposter.ports.event_bus import InMemoryEventBus
from imposter.ports.game_store import InMemoryGameStore
from imposter.telemetry.setup import set_telemetry_defaults
from imposter.telemetry.spans import GameTracePlugin

set_telemetry_defaults()

setup = GameSetup.load()
store = InMemoryGameStore()
sessions = GameSessions(
    setup=setup,
    bus=InMemoryEventBus(),
    store=store,
    default_request=GameRequest(
        config=GameConfig(players=setup.player_configs(DEFAULT_MODEL_IDS))
    ),
)

root_agent = game_workflow(sessions=sessions)

trace_plugin = GameTracePlugin(find_game=store.get)

app = App(name=APP_NAME, root_agent=root_agent, plugins=[trace_plugin])
