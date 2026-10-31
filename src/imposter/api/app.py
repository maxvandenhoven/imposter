"""The HTTP API: ADK's API server for the game app, plus the catalog route.

ADK serves the app of `imposter/agent.py`, the same app `adk web` loads, in single agent
mode, with sessions in memory. A client starts a game in two calls:

1. `POST /apps/imposter/users/{user_id}/sessions` with the `GameRequest` as JSON in the
   initial state, under `game:request`. The session id is the game id.
2. `POST /run_sse` with that session and `"streaming": true`, which plays the game and
   streams its ADK events as server-sent events while it runs.

The game runs as long as that request is open. When the client goes away, ADK cancels
the run and the game is aborted. `GET /catalog` lists what the setup screen offers.
"""

from pathlib import Path

from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

from imposter.api.catalog import catalog_router
from imposter.models.catalog import ModelCatalog
from imposter.telemetry.setup import exporter_from_environment, setup_telemetry
from imposter.words.picker import WordPicker

PACKAGE_DIR = Path(__file__).parents[1]
"""The package directory, which holds `agent.py`: ADK serves it as the only app."""


def create_app() -> FastAPI:
    """Build the API app, with telemetry set up from the environment.

    Returns:
        The app, for uvicorn (`uvicorn --factory imposter.api.app:create_app`).
    """
    setup_telemetry(exporter_from_environment())
    app = get_fast_api_app(
        agents_dir=str(PACKAGE_DIR), web=False, use_local_storage=False
    )
    app.include_router(
        catalog_router(catalog=ModelCatalog.load(), picker=WordPicker.load())
    )

    return app
