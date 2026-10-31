import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from imposter.api.identity import IapIdentityMiddleware
from imposter.telemetry.identity import REQUEST_USER


async def whoami(request: Request) -> PlainTextResponse:
    return PlainTextResponse(REQUEST_USER.get() or "nobody")


@pytest.fixture(scope="function")
def client() -> TestClient:
    app = Starlette(routes=[Route("/whoami", whoami)])
    app.add_middleware(IapIdentityMiddleware)

    return TestClient(app)


def test_user_comes_from_the_iap_header(client: TestClient) -> None:
    headers = {"X-Goog-Authenticated-User-Email": "accounts.google.com:max@example.com"}

    assert client.get("/whoami", headers=headers).text == "max@example.com"
    assert REQUEST_USER.get() is None


def test_dev_user_is_used_without_the_header(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get("/whoami").text == "nobody"

    monkeypatch.setenv("IMPOSTER_DEV_USER", "dev@example.com")

    assert client.get("/whoami").text == "dev@example.com"


def test_header_wins_over_the_dev_user(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IMPOSTER_DEV_USER", "dev@example.com")
    headers = {"X-Goog-Authenticated-User-Email": "accounts.google.com:max@example.com"}

    assert client.get("/whoami", headers=headers).text == "max@example.com"
