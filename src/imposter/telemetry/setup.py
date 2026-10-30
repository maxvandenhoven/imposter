import json
import logging
import os
import sys
from enum import StrEnum

import google.auth
from google.adk.telemetry.google_cloud import get_gcp_exporters, get_gcp_resource
from google.adk.telemetry.setup import OTelHooks, maybe_set_otel_providers
from opentelemetry import trace
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
"""The OAuth scope of the credentials that export to Google Cloud."""

CONTENT_CAPTURE_DEFAULTS = {
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "EVENT_ONLY",
    "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "false",
    "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
}
"""Prompts and completions go to Cloud Logging as events, linked to their spans, and
stay out of span attributes. Variables that are already set win."""

TRACE_URL = (
    "https://console.cloud.google.com/traces/explorer?project={project}&tid={trace_id}"
)
"""The Trace Explorer page of one trace."""


class TelemetryExporter(StrEnum):
    """Where traces and logs go."""

    CLOUD = "cloud"
    CONSOLE = "console"
    NONE = "none"


class JsonLogFormatter(logging.Formatter):
    """Formats log records as JSON lines that Cloud Logging reads as structured logs.

    The trace and span fields link a record to the span that was current when it was
    logged, so app logs show up next to their trace.

    Attributes:
        project: The Google Cloud project of the traces, if known.
    """

    def __init__(self, project: str | None = None) -> None:
        """Initialize the formatter.

        Args:
            project: The Google Cloud project of the traces, if known.
        """
        super().__init__()
        self.project = project

    def format(self, record: logging.LogRecord) -> str:
        """Format one record as a JSON object on one line.

        Args:
            record: The log record.

        Returns:
            The JSON line.
        """
        entry = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)

        context = trace.get_current_span().get_span_context()

        if context.is_valid and self.project:
            trace_id = trace.format_trace_id(context.trace_id)
            entry["logging.googleapis.com/trace"] = (
                f"projects/{self.project}/traces/{trace_id}"
            )
            entry["logging.googleapis.com/spanId"] = trace.format_span_id(context.span_id)
            entry["logging.googleapis.com/trace_sampled"] = context.trace_flags.sampled

        return json.dumps(entry)


def setup_telemetry(
    *, exporter: TelemetryExporter, json_logs: bool = False
) -> str | None:
    """Set up tracing, content capture and logging, once per process.

    The `cloud` exporter uses ADK's Google Cloud setup, the one behind
    `get_fast_api_app(otel_to_cloud=True)`: spans go to Cloud Trace and the prompt and
    completion events to Cloud Logging, over OTLP to `telemetry.googleapis.com` with
    Application Default Credentials. The `console` exporter prints spans to stderr.

    Args:
        exporter: Where traces and logs go.
        json_logs: Whether app logs are JSON lines with trace fields, as on Cloud Run.

    Returns:
        The Google Cloud project the traces go to, `None` unless the exporter is `cloud`.

    Raises:
        ValueError: When the exporter is `cloud` but no project is known.
    """
    for name, value in CONTENT_CAPTURE_DEFAULTS.items():
        os.environ.setdefault(name, value)

    project = None

    match exporter:
        case TelemetryExporter.CLOUD:
            credentials, project = google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
            project = os.environ.get("GOOGLE_CLOUD_PROJECT") or project

            if not project:
                message = "Set GOOGLE_CLOUD_PROJECT to export traces to Google Cloud."
                raise ValueError(message)

            maybe_set_otel_providers(
                otel_hooks_to_setup=[
                    get_gcp_exporters(
                        enable_cloud_tracing=True,
                        enable_cloud_logging=True,
                        google_auth=(credentials, project),
                    )
                ],
                otel_resource=get_gcp_resource(project),
            )
        case TelemetryExporter.CONSOLE:
            processor = SimpleSpanProcessor(ConsoleSpanExporter(out=sys.stderr))
            maybe_set_otel_providers(
                otel_hooks_to_setup=[OTelHooks(span_processors=[processor])]
            )
        case TelemetryExporter.NONE:
            pass

    if json_logs:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonLogFormatter(project))
        logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)

    return project


def trace_url(*, project: str, trace_id: int) -> str:
    """Build the Trace Explorer link of a trace.

    Args:
        project: The Google Cloud project of the trace.
        trace_id: The OpenTelemetry trace id.

    Returns:
        The link.
    """
    return TRACE_URL.format(project=project, trace_id=trace.format_trace_id(trace_id))
