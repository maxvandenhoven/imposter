"""The HTTP API: ADK's API server for the game app, plus the catalog route.

ADK serves the app of `imposter/agent.py`, the same app `adk web` loads, in single agent
mode, with sessions in memory. A client starts a game in two calls:

1. `POST /apps/imposter/users/{user_id}/sessions` with the `GameRequest` as JSON in the
   initial state, under `game:request`. The session id is the game id.
2. `POST /run_sse` with that session and `"streaming": true`, which plays the game and
   streams its ADK events as server-sent events while it runs.

The game runs as long as that request is open. When the client goes away, ADK cancels
the run and the game is aborted. `GET /catalog` lists what the setup screen offers, `GET
/traces/{game_id}` links to the trace of a game, and the built frontend is served at
`/` when it exists.
"""

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app

from imposter.agent import trace_plugin
from imposter.api.catalog import catalog_router
from imposter.api.identity import IapIdentityMiddleware
from imposter.api.trace import trace_router
from imposter.models.catalog import ModelCatalog
from imposter.telemetry.setup import exporter_from_environment, setup_telemetry
from imposter.words.picker import WordPicker

PACKAGE_DIR = Path(__file__).parents[1]
"""The package directory, which holds `agent.py`: ADK serves it as the only app."""

FRONTEND_DIR_ENV = "IMPOSTER_FRONTEND_DIR"
"""The environment variable with the directory of the built frontend."""

ALLOW_ORIGINS_ENV = "IMPOSTER_ALLOW_ORIGINS"
"""The environment variable with extra allowed origins, separated by commas."""

DEFAULT_FRONTEND_DIR = Path("frontend/dist")
"""Where `make frontend` builds the frontend, relative to the repository root."""

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Build the API app, with telemetry set up from the environment.

    The built frontend is served at `/` from the directory in `IMPOSTER_FRONTEND_DIR`,
    or from `frontend/dist` in the working directory, when that directory exists. ADK
    only accepts browser requests whose `Origin` is the server's own, so a proxy that
    serves the app under another origin (`gcloud run services proxy` on localhost) needs
    that origin in `IMPOSTER_ALLOW_ORIGINS`.

    Returns:
        The app, for uvicorn (`uvicorn --factory imposter.api.app:create_app`).
    """
    project = setup_telemetry(exporter_from_environment())
    origins = [o.strip() for o in os.environ.get(ALLOW_ORIGINS_ENV, "").split(",")]
    app = get_fast_api_app(
        agents_dir=str(PACKAGE_DIR),
        web=False,
        use_local_storage=False,
        allow_origins=[o for o in origins if o] or None,
    )
    app.add_middleware(IapIdentityMiddleware)
    app.include_router(
        catalog_router(catalog=ModelCatalog.load(), picker=WordPicker.load())
    )
    app.include_router(trace_router(trace_ids=trace_plugin.trace_ids, project=project))
    # Mounted last, so every API route takes precedence over the files.
    frontend_dir = Path(os.environ.get(FRONTEND_DIR_ENV) or DEFAULT_FRONTEND_DIR)

    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    else:
        logger.info("No frontend build at `%s`, serving the API only.", frontend_dir)

    return app
