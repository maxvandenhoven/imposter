import os
from typing import Any

import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from imposter.telemetry import setup
from imposter.telemetry.setup import (
    TELEMETRY_DEFAULTS,
    TelemetryExporter,
    setup_telemetry,
    trace_url,
)


@pytest.fixture(scope="function")
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset the telemetry variables, and restore them after the test."""
    for name in [*TELEMETRY_DEFAULTS, "OTEL_RESOURCE_ATTRIBUTES"]:
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


@pytest.fixture(scope="function")
def providers(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Record the hooks handed to ADK instead of setting the global providers."""
    calls: list[Any] = []
    monkeypatch.setattr(setup, "maybe_set_otel_providers", calls.append)

    return calls


@pytest.mark.usefixtures("clean_environment")
def test_defaults_do_not_override_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "true")

    project = setup_telemetry(TelemetryExporter.NONE)

    assert project is None
    assert os.environ["OTEL_SERVICE_NAME"] == "imposter"
    assert (
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] == "EVENT_ONLY"
    )
    assert os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"] == "gen_ai_latest_experimental"
    assert os.environ["ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"] == "true"


@pytest.mark.usefixtures("clean_environment")
def test_cloud_exporter_hands_the_adk_google_cloud_exporters_to_adk(
    monkeypatch: pytest.MonkeyPatch, providers: list[Any]
) -> None:
    options: dict[str, Any] = {}

    def gcp_exporters(**given: Any) -> str:
        options.update(given)
        return "gcp hooks"

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "sandbox")
    monkeypatch.setattr(setup, "get_gcp_exporters", gcp_exporters)

    project = setup_telemetry(TelemetryExporter.CLOUD)

    assert project == "sandbox"
    assert options == {"enable_cloud_tracing": True, "enable_cloud_logging": True}
    assert providers == [["gcp hooks"]]
    assert os.environ["OTEL_RESOURCE_ATTRIBUTES"] == "gcp.project_id=sandbox"


def test_console_exporter_prints_spans(providers: list[Any]) -> None:
    project = setup_telemetry(TelemetryExporter.CONSOLE)
    [[hooks]] = providers

    assert project is None
    assert isinstance(hooks.span_processors[0], SimpleSpanProcessor)


def test_cloud_exporter_needs_a_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

    with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
        setup_telemetry(TelemetryExporter.CLOUD)


def test_trace_url_opens_the_trace_in_trace_explorer() -> None:
    url = trace_url(project="sandbox", trace_id=255)

    assert url == (
        "https://console.cloud.google.com/traces/explorer?project=sandbox"
        "&tid=000000000000000000000000000000ff"
    )
