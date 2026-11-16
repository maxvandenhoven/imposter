from google.adk.workflow import Workflow

from imposter.agent import app, builder, root_agent, trace_plugin
from imposter.orchestration.play import APP_NAME


def test_root_agent_is_the_game_workflow_with_a_default_game() -> None:
    assert isinstance(root_agent, Workflow)
    assert builder.default_request is not None
    assert len(builder.default_request.config.players) >= 3


def test_app_serves_the_workflow_with_the_trace_plugin() -> None:
    assert app.name == APP_NAME
    assert app.root_agent is root_agent
    assert app.plugins == [trace_plugin]
