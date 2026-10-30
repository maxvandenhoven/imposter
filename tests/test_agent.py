from google.adk.workflow import Workflow

from imposter.agent import root_agent
from imposter.config import GamePhase
from imposter.orchestration.runner_workflow import GamePhaseNode


def test_root_agent_is_the_game_workflow_with_a_default_game() -> None:
    assert isinstance(root_agent, Workflow)
    assert root_agent.graph is not None

    nodes = [node for node in root_agent.graph.nodes if isinstance(node, GamePhaseNode)]

    assert {node.phase for node in nodes} == set(GamePhase)

    request = nodes[0].sessions.default_request

    assert request is not None
    assert len(request.config.players) >= 3
