"""The `root_agent` that `adk web src` loads: the game workflow, one game per session."""

from imposter.config import GameConfig
from imposter.orchestration.runner_workflow import GameSessions, game_workflow
from imposter.orchestration.setup import DEFAULT_MODEL_IDS, GameRequest, GameSetup
from imposter.ports.event_bus import InMemoryEventBus
from imposter.ports.game_store import InMemoryGameStore

setup = GameSetup.load()

root_agent = game_workflow(
    sessions=GameSessions(
        setup=setup,
        bus=InMemoryEventBus(),
        store=InMemoryGameStore(),
        default_request=GameRequest(
            config=GameConfig(players=setup.player_configs(DEFAULT_MODEL_IDS))
        ),
    )
)
