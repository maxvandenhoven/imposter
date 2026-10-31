"""The OpenAPI schema of the API app, with the game types that ADK leaves untyped.

ADK types the session state and the `custom_metadata` of its events as free objects, so
the schema it builds says nothing about the `GameRequest` a client puts in the state or
the engine events it reads from the stream. `openapi_schema` adds both to the components,
so the frontend generates its types for them from the same file (`make api-client`).
"""

from typing import Any

from fastapi import FastAPI
from pydantic import TypeAdapter
from pydantic.json_schema import JsonSchemaMode

from imposter.engine.events import GameEvent
from imposter.orchestration.setup import GameRequest

REF_TEMPLATE = "#/components/schemas/{model}"
"""Where OpenAPI keeps the schemas that others refer to."""


def game_schemas() -> dict[str, Any]:
    """Build the JSON schemas of the game request and the engine events.

    The request is described as a client sends it and the events as the server sends
    them, so fields with defaults are required in the events.

    Returns:
        The schemas by component name, among them `GameRequest` and `GameEvent`, the
        union of the engine events.
    """
    inputs: list[tuple[str, JsonSchemaMode, TypeAdapter[Any]]] = [
        ("request", "validation", TypeAdapter(GameRequest)),
        ("event", "serialization", TypeAdapter(GameEvent)),
    ]
    _, definitions = TypeAdapter.json_schemas(inputs, ref_template=REF_TEMPLATE)

    return definitions["$defs"]


def openapi_schema(app: FastAPI) -> dict[str, Any]:
    """Build the OpenAPI schema of the app with the game schemas in its components.

    Args:
        app: The API app.

    Returns:
        The schema, ready to be written as JSON.

    Raises:
        ValueError: When a game schema has the name of a different schema of the app.
    """
    schema = app.openapi()
    components = schema.setdefault("components", {}).setdefault("schemas", {})

    for name, definition in game_schemas().items():
        if components.get(name, definition) != definition:
            message = f"The game schema {name} clashes with a schema of the app."
            raise ValueError(message)

        components[name] = definition

    return schema
