from collections.abc import Mapping

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from imposter.telemetry.setup import trace_url


class GameTraceResponse(BaseModel):
    """Where the trace of a game can be seen.

    Attributes:
        url: The Trace Explorer link of the game's run, `None` when traces are not sent
            to Google Cloud or the run has not started.
    """

    model_config = ConfigDict(frozen=True)

    url: str | None


def trace_router(*, trace_ids: Mapping[str, int], project: str | None) -> APIRouter:
    """Build the router of the trace route.

    Args:
        trace_ids: The trace id of each game run so far, by game id, which the game
            trace plugin fills while games run.
        project: The Google Cloud project the traces go to, `None` when they are not
            sent to Google Cloud.

    Returns:
        The router.
    """
    router = APIRouter()

    @router.get(
        "/traces/{game_id}",
        description="Link to the trace of a game in Cloud Trace, once its run started.",
    )
    async def read_trace(game_id: str) -> GameTraceResponse:
        trace_id = trace_ids.get(game_id)

        if project is None or trace_id is None:
            return GameTraceResponse(url=None)

        return GameTraceResponse(url=trace_url(project=project, trace_id=trace_id))

    return router
