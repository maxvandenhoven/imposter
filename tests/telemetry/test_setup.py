import json
import logging
import os
from typing import Any

import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from imposter.telemetry import setup
from imposter.telemetry.setup import (
    CONTENT_CAPTURE_DEFAULTS,
    JsonLogFormatter,
    TelemetryExporter,
    setup_telemetry,
    trace_url,
)
from imposter.telemetry.spans import TRACER


def log_record(message: str) -> logging.LogRecord:
    """Build an info record of the `imposter` logger."""
    return logging.LogRecord("imposter", logging.INFO, __file__, 1, message, None, None)


def test_content_capture_defaults_do_not_override_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in CONTENT_CAPTURE_DEFAULTS:
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)

    monkeypatch.setenv("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "true")

    project = setup_telemetry(exporter=TelemetryExporter.NONE)

    assert project is None
    assert (
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] == "EVENT_ONLY"
    )
    assert os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"] == "gen_ai_latest_experimental"
    assert os.environ["ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"] == "true"


def test_cloud_exporter_uses_the_adk_google_cloud_exporters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def gcp_exporters(**options: object) -> str:
        calls["exporters"] = options
        return "gcp hooks"

    def set_providers(**options: object) -> None:
        calls["providers"] = options

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "sandbox")
    monkeypatch.setattr(setup.google.auth, "default", lambda scopes: ("creds", None))
    monkeypatch.setattr(setup, "get_gcp_exporters", gcp_exporters)
    monkeypatch.setattr(setup, "maybe_set_otel_providers", set_providers)

    project = setup_telemetry(exporter=TelemetryExporter.CLOUD)

    assert project == "sandbox"
    assert calls["exporters"] == {
        "enable_cloud_tracing": True,
        "enable_cloud_logging": True,
        "google_auth": ("creds", "sandbox"),
    }
    assert calls["providers"]["otel_hooks_to_setup"] == ["gcp hooks"]


def test_console_exporter_prints_spans_and_logs_are_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def set_providers(**options: object) -> None:
        calls["providers"] = options

    def basic_config(**options: object) -> None:
        calls["logging"] = options

    monkeypatch.setattr(setup, "maybe_set_otel_providers", set_providers)
    monkeypatch.setattr(setup.logging, "basicConfig", basic_config)

    project = setup_telemetry(exporter=TelemetryExporter.CONSOLE, json_logs=True)
    [hooks] = calls["providers"]["otel_hooks_to_setup"]
    [handler] = calls["logging"]["handlers"]

    assert project is None
    assert isinstance(hooks.span_processors[0], SimpleSpanProcessor)
    assert isinstance(handler.formatter, JsonLogFormatter)


def test_cloud_exporter_needs_a_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.setattr(setup.google.auth, "default", lambda scopes: ("creds", None))

    with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
        setup_telemetry(exporter=TelemetryExporter.CLOUD)


def test_json_logs_link_records_to_the_current_span(
    span_exporter: InMemorySpanExporter,
) -> None:
    formatter = JsonLogFormatter(project="sandbox")

    with TRACER.start_as_current_span("work") as span:
        entry = json.loads(formatter.format(log_record("Inside.")))

    context = span.get_span_context()
    outside = json.loads(formatter.format(log_record("Outside.")))

    assert entry["severity"] == "INFO"
    assert entry["message"] == "Inside."
    assert entry["logging.googleapis.com/trace"] == (
        f"projects/sandbox/traces/{context.trace_id:032x}"
    )
    assert entry["logging.googleapis.com/spanId"] == f"{context.span_id:016x}"
    assert "logging.googleapis.com/trace" not in outside


def test_trace_url_opens_the_trace_in_trace_explorer() -> None:
    url = trace_url(project="sandbox", trace_id=255)

    assert url == (
        "https://console.cloud.google.com/traces/explorer?project=sandbox"
        "&tid=000000000000000000000000000000ff"
    )
