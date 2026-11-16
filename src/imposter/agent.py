"""The game workflow as the ADK `app` of `adk web src` and the API, one game per session.

The app carries the plugin that puts the game attributes on the root span of a game
and notes the trace id of each game, which the API links to.
`adk web --otel_to_cloud` exports the traces, and the telemetry defaults make ADK log
the prompts and completions, as the CLI does.
"""

from imposter.orchestration.play import game_app
from imposter.orchestration.workflow import GameWorkflowBuilder
from imposter.telemetry.setup import set_telemetry_defaults
from imposter.telemetry.spans import GameTracePlugin

set_telemetry_defaults()

builder = GameWorkflowBuilder.load(with_default_request=True)

root_agent = builder.build()

trace_plugin = GameTracePlugin()

app = game_app(workflow=root_agent, plugins=[trace_plugin])
