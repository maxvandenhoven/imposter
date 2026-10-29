"""The `root_agent` that `adk web src/imposter` loads: each new session plays a game."""

from imposter.config import GameConfig
from imposter.orchestration.adk_runner import AGENT_NAME
from imposter.orchestration.runner_agent import GameRunnerAgent
from imposter.orchestration.setup import DEFAULT_MODEL_IDS, GameRequest, GameSetup

setup = GameSetup.load()

root_agent = GameRunnerAgent(
    name=AGENT_NAME,
    description="Plays a game of Imposter between LLM players, one game per session.",
    setup=setup,
    default_request=GameRequest(
        config=GameConfig(players=setup.player_configs(DEFAULT_MODEL_IDS))
    ),
)
