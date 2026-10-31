from fastapi import FastAPI
from fastapi.testclient import TestClient

from imposter.api.trace import trace_router

TRACE_ID = 0x0123456789ABCDEF0123456789ABCDEF


def trace_client(*, project: str | None) -> TestClient:
    """A client of an app with only the trace route, which knows the trace of `game-1`."""
    app = FastAPI()
    app.include_router(trace_router(trace_ids={"game-1": TRACE_ID}, project=project))

    return TestClient(app)


def test_trace_links_to_the_trace_explorer_once_the_run_started() -> None:
    client = trace_client(project="sandbox")

    assert client.get("/traces/game-1").json() == {
        "url": "https://console.cloud.google.com/traces/explorer"
        "?project=sandbox&tid=0123456789abcdef0123456789abcdef"
    }
    assert client.get("/traces/game-2").json() == {"url": None}


def test_trace_has_no_link_when_traces_stay_local() -> None:
    assert trace_client(project=None).get("/traces/game-1").json() == {"url": None}
