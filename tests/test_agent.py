from imposter.agent import root_agent
from imposter.orchestration.runner_agent import GameRunnerAgent


def test_root_agent_plays_a_default_game_per_session() -> None:
    assert isinstance(root_agent, GameRunnerAgent)
    assert root_agent.default_request is not None
    assert len(root_agent.default_request.config.players) >= 3
