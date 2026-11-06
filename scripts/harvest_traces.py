"""Export played games from Cloud Logging and Cloud Trace for the evals.

Downloads the prompt and completion log entries that ADK writes for every model call
(`gen_ai.client.inference.operation.details`) to `logs.jsonl`, and every trace that
holds a game (a span with the `imposter.game.id` attribute) to `traces/<trace id>.json`.
The eval set builder (`scripts/build_evalsets.py`) reads both. Cloud Logging keeps the
entries for 30 days by default, so exports are the long-term record of past games.

Usage: `uv run --env-file .env python scripts/harvest_traces.py [--since 2026-10-01]`.
The output goes to `evals/raw/<today>/`, which git ignores. Credentials come from ADC
(`gcloud auth application-default login`).
"""

import datetime
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Any

import google.auth
import typer
from google.auth.transport.requests import AuthorizedSession

LOGGING_URL = "https://logging.googleapis.com/v2/entries:list"
TRACE_URL = "https://cloudtrace.googleapis.com/v1/projects/{project}/traces"
LOG_NAME = "gen_ai.client.inference.operation.details"
GAME_ATTRIBUTE = "imposter.game.id"
TRACE_FILTER = "span:invoke_workflow"
PAGE_SIZE = 1000
DOWNLOAD_WORKERS = 16
RAW_DIR = Path("evals/raw")

logger = logging.getLogger("harvest_traces")


def authorized_session() -> AuthorizedSession:
    """Open an HTTP session that signs requests with ADC.

    Returns:
        The session.
    """
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    return AuthorizedSession(credentials)


def log_entries(
    *, session: AuthorizedSession, project: str, since: datetime.date
) -> list[dict[str, Any]]:
    """List the prompt and completion log entries of every model call since a date.

    Args:
        session: The signed HTTP session.
        project: The GCP project.
        since: The first day to include.

    Returns:
        The entries, oldest first.
    """
    entries: list[dict[str, Any]] = []
    body: dict[str, Any] = {
        "resourceNames": [f"projects/{project}"],
        "filter": f'logName:"{LOG_NAME}" timestamp>="{since.isoformat()}T00:00:00Z"',
        "orderBy": "timestamp asc",
        "pageSize": PAGE_SIZE,
    }

    while True:
        response = session.post(LOGGING_URL, json=body)
        response.raise_for_status()
        page = response.json()
        entries.extend(page.get("entries", []))

        if "nextPageToken" not in page:
            return entries

        body["pageToken"] = page["nextPageToken"]


def trace_ids(
    *, session: AuthorizedSession, project: str, since: datetime.date
) -> list[str]:
    """List the traces since a date that run a workflow, which every game does.

    Args:
        session: The signed HTTP session.
        project: The GCP project.
        since: The first day to include.

    Returns:
        The trace ids.
    """
    ids: list[str] = []
    params = {
        "view": "MINIMAL",
        "startTime": f"{since.isoformat()}T00:00:00Z",
        "filter": TRACE_FILTER,
        "pageSize": PAGE_SIZE,
    }

    while True:
        response = session.get(TRACE_URL.format(project=project), params=params)
        response.raise_for_status()
        page = response.json()
        ids.extend(trace["traceId"] for trace in page.get("traces", []))

        if "nextPageToken" not in page:
            return ids

        params["pageToken"] = page["nextPageToken"]


def game_trace(
    *, session: AuthorizedSession, project: str, trace_id: str
) -> dict[str, Any] | None:
    """Download one trace if it holds a game.

    Args:
        session: The signed HTTP session.
        project: The GCP project.
        trace_id: The trace id.

    Returns:
        The trace with all its spans, or `None` when no span carries a game id.
    """
    response = session.get(f"{TRACE_URL.format(project=project)}/{trace_id}")
    response.raise_for_status()
    trace = response.json()
    is_game = any(GAME_ATTRIBUTE in span.get("labels", {}) for span in trace["spans"])

    return trace if is_game else None


app = typer.Typer(add_completion=False)


@app.command()
def main(
    project: Annotated[
        str,
        typer.Option(envvar="GOOGLE_CLOUD_PROJECT", help="GCP project ID to read from."),
    ],
    since: Annotated[
        datetime.datetime, typer.Option(formats=["%Y-%m-%d"], help="First day to export.")
    ] = datetime.datetime(2026, 10, 1),
    output: Annotated[
        Path | None, typer.Option(help="Output folder. Default: `evals/raw/<today>`.")
    ] = None,
) -> None:
    """Export the log entries and game traces since a day to a folder."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    folder = output or RAW_DIR / datetime.date.today().isoformat()
    (folder / "traces").mkdir(parents=True, exist_ok=True)
    session = authorized_session()
    first_day = since.date()

    entries = log_entries(session=session, project=project, since=first_day)

    with (folder / "logs.jsonl").open("w") as file:
        file.writelines(json.dumps(entry) + "\n" for entry in entries)

    ids = trace_ids(session=session, project=project, since=first_day)

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        traces = pool.map(
            lambda trace_id: game_trace(
                session=session, project=project, trace_id=trace_id
            ),
            ids,
        )
        games = [trace for trace in traces if trace is not None]

    for trace in games:
        (folder / "traces" / f"{trace['traceId']}.json").write_text(json.dumps(trace))

    logger.info(
        "Exported %d log entries and %d game traces (of %d workflow traces) to %s.",
        len(entries),
        len(games),
        len(ids),
        folder,
    )


if __name__ == "__main__":
    app()
