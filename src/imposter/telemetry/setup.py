import os
import sys
from enum import StrEnum

from google.adk.telemetry.google_cloud import get_gcp_exporters
from google.adk.telemetry.setup import OTelHooks, maybe_set_otel_providers
from opentelemetry import trace
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

TELEMETRY_DEFAULTS = {
    "OTEL_SERVICE_NAME": "imposter",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "EVENT_ONLY",
    "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "false",
    "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
}
"""The service name of the traces, and content capture: ADK logs the prompts and
completions to Cloud Logging as events linked to their spans, and keeps them out of span
attributes. Variables that are already set win."""

TRACE_URL = (
    "https://console.cloud.google.com/traces/explorer?project={project}&tid={trace_id}"
)
"""The Trace Explorer page of one trace."""


class TelemetryExporter(StrEnum):
    """Where traces and logs go."""

    CLOUD = "cloud"
    CONSOLE = "console"
    NONE = "none"


def set_telemetry_defaults() -> None:
    """Set the telemetry environment variables that are not set yet."""
    for name, value in TELEMETRY_DEFAULTS.items():
        os.environ.setdefault(name, value)


def setup_telemetry(exporter: TelemetryExporter) -> str | None:
    """Set up tracing and content capture, once per process.

    The `cloud` exporter follows ADK's tracing guide: `get_gcp_exporters` handed to
    `maybe_set_otel_providers`. Spans go to Cloud Trace and ADK's prompt and completion
    events to Cloud Logging, over OTLP to `telemetry.googleapis.com` with Application
    Default Credentials. The `console` exporter prints spans to stderr.

    Args:
        exporter: Where traces and logs go.

    Returns:
        The Google Cloud project the traces go to, `None` unless the exporter is `cloud`.

    Raises:
        ValueError: When the exporter is `cloud` but `GOOGLE_CLOUD_PROJECT` is not set.
    """
    set_telemetry_defaults()

    match exporter:
        case TelemetryExporter.CLOUD:
            project = os.environ.get("GOOGLE_CLOUD_PROJECT")

            if not project:
                message = "Set GOOGLE_CLOUD_PROJECT to export traces to Google Cloud."
                raise ValueError(message)

            # The telemetry API takes the project of the spans from this attribute.
            os.environ.setdefault("OTEL_RESOURCE_ATTRIBUTES", f"gcp.project_id={project}")
            exporters = get_gcp_exporters(
                enable_cloud_tracing=True, enable_cloud_logging=True
            )
            maybe_set_otel_providers([exporters])

            return project
        case TelemetryExporter.CONSOLE:
            processor = SimpleSpanProcessor(ConsoleSpanExporter(out=sys.stderr))
            maybe_set_otel_providers([OTelHooks(span_processors=[processor])])
        case TelemetryExporter.NONE:
            pass

    return None


def trace_url(*, project: str, trace_id: int) -> str:
    """Build the Trace Explorer link of a trace.

    Args:
        project: The Google Cloud project of the trace.
        trace_id: The OpenTelemetry trace id.

    Returns:
        The link.
    """
    return TRACE_URL.format(project=project, trace_id=trace.format_trace_id(trace_id))
