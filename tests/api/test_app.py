import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from conftest import FakeGameSetup
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from imposter import agent
from imposter.api.app import create_app
from imposter.config import GameConfig, PlayerConfig
from imposter.models.catalog import ModelCatalog
from imposter.orchestration.runner_workflow import GAME_EVENT_METADATA_KEY
from imposter.orchestration.setup import DEFAULT_MODEL_IDS, GameRequest

SESSIONS_PATH = "/apps/imposter/users/tester/sessions"


@pytest.fixture(scope="module")
def client(span_exporter: InMemorySpanExporter) -> Iterator[TestClient]:
    """A client of the API app, without telemetry.

    ADK sets a tracer provider when it builds the app unless one is set, and only the
    first one counts, so the collecting provider of the other tests is set first.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("IMPOSTER_TELEMETRY", "none")

        with TestClient(create_app()) as client:
            yield client


def stream_game(client: TestClient, request: GameRequest) -> list[dict[str, Any]]:
    """Create a session with the request in state, run it over SSE and collect events."""
    state = {"game:request": request.model_dump(mode="json")}
    session = client.post(SESSIONS_PATH, json={"state": state}).json()
    body = {
        "app_name": "imposter",
        "user_id": "tester",
        "session_id": session["id"],
        "new_message": {"role": "user", "parts": [{"text": "Play the game."}]},
        "streaming": True,
    }

    with client.stream("POST", "/run_sse", json=body) as response:
        return [
            json.loads(line.removeprefix("data: "))
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]


def test_catalog_lists_the_models_categories_and_default_lineup(
    client: TestClient,
) -> None:
    catalog = client.get("/catalog").json()

    assert [model["id"] for model in catalog["models"]] == [
        entry.id for entry in ModelCatalog.load().entries
    ]
    assert "adk_model" not in catalog["models"][0]
    assert catalog["categories"]
    assert "words" not in catalog["categories"][0]
    assert catalog["default_lineup"] == DEFAULT_MODEL_IDS


def test_adk_serves_only_the_game_app(client: TestClient) -> None:
    assert client.get("/list-apps").json() == ["imposter"]


def test_game_streams_its_engine_events_over_run_sse(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent.sessions, "setup", FakeGameSetup())
    players = [PlayerConfig(model_id=model_id) for model_id in DEFAULT_MODEL_IDS]
    request = GameRequest(config=GameConfig(players=players, seed=5))

    events = stream_game(client, request)

    game_events = [
        event["customMetadata"][GAME_EVENT_METADATA_KEY]
        for event in events
        if GAME_EVENT_METADATA_KEY in (event.get("customMetadata") or {})
    ]
    types = [event["type"] for event in game_events]
    turns = {
        event["nodeInfo"]["path"].split("/")[2]
        for event in events
        if "_turn@" in event["nodeInfo"]["path"]
    }
    assert types[0] == "game_started"
    assert types[-1] == "game_finished"
    assert [event["seq"] for event in game_events] == list(range(len(game_events)))
    assert types.index("turn_started") < types.index("clue_given")
    assert turns == {f"player_{seat}_turn@1" for seat in range(len(players))}


@pytest.mark.usefixtures("span_exporter")
def test_frontend_is_served_at_the_root_after_the_api_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "index.html").write_text("<p>Imposter</p>")
    (tmp_path / "logos").mkdir()
    (tmp_path / "logos" / "gemini.svg").write_text("<svg></svg>")
    monkeypatch.setenv("IMPOSTER_TELEMETRY", "none")
    monkeypatch.setenv("IMPOSTER_FRONTEND_DIR", str(tmp_path))

    with TestClient(create_app()) as client:
        assert client.get("/").text == "<p>Imposter</p>"
        assert client.get("/logos/gemini.svg").text == "<svg></svg>"
        assert client.get("/catalog").json()["models"]
        assert client.get("/list-apps").json() == ["imposter"]
        assert client.get("/health").status_code == 200
        assert client.get("/apps/imposter/unknown").status_code == 404
        assert client.get("/missing.js").status_code == 404


@pytest.mark.usefixtures("span_exporter")
def test_api_is_served_alone_without_a_frontend_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IMPOSTER_TELEMETRY", "none")
    monkeypatch.setenv("IMPOSTER_FRONTEND_DIR", str(tmp_path / "missing"))

    with TestClient(create_app()) as client:
        assert client.get("/").status_code == 404
        assert client.get("/catalog").status_code == 200
