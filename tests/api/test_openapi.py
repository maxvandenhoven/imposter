from typing import Any

import pytest
from fastapi import FastAPI

from imposter.api.openapi import game_schemas, openapi_schema
from imposter.engine.events import GAME_EVENT_ADAPTER


def test_game_schemas_hold_the_request_and_every_engine_event() -> None:
    schemas = game_schemas()

    event_types = set(schemas["GameEvent"]["discriminator"]["mapping"])
    assert "GameRequest" in schemas
    assert "GameConfig" in schemas
    assert "turn_started" in event_types
    assert len(event_types) == len(GAME_EVENT_ADAPTER.json_schema()["oneOf"])


def test_event_schemas_require_the_fields_with_defaults() -> None:
    required = game_schemas()["ClueGivenEvent"]["required"]

    assert {"seq", "round", "visibility", "rejection_reason"} <= set(required)


def test_openapi_schema_adds_the_game_schemas_to_the_components() -> None:
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ping": "pong"}

    schema = openapi_schema(app)

    assert "/ping" in schema["paths"]
    assert "GameEvent" in schema["components"]["schemas"]


def test_openapi_schema_rejects_a_clashing_schema_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    original = app.openapi

    def openapi() -> dict[str, Any]:
        schema = original()
        schema["components"] = {"schemas": {"GameRequest": {"type": "string"}}}

        return schema

    monkeypatch.setattr(app, "openapi", openapi)

    with pytest.raises(ValueError, match="clashes"):
        openapi_schema(app)
