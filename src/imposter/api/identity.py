import os

from starlette.types import ASGIApp, Receive, Scope, Send

from imposter.telemetry.identity import REQUEST_USER
from imposter.utils.identity import iap_user

IAP_USER_HEADER = b"x-goog-authenticated-user-email"
"""The header in which IAP passes the identity of the signed-in user."""

DEV_USER_ENV = "IMPOSTER_DEV_USER"
"""The environment variable with the user to assume when IAP sends no header."""


class IapIdentityMiddleware:
    """An ASGI middleware that makes the IAP user of a request available to the game.

    The header is trusted because IAP is the only way to reach the deployed service.
    Without the header, for example on a laptop, the user in `IMPOSTER_DEV_USER` is used
    when it is set. The user is stored in `REQUEST_USER` while the request is served,
    which includes the whole game run of `/run_sse`.

    Attributes:
        app: The ASGI app that is wrapped.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the middleware.

        Args:
            app: The ASGI app to wrap.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve a request with the user of its IAP header stored.

        Args:
            scope: The ASGI scope of the request.
            receive: Receives the messages of the request.
            send: Sends the messages of the response.
        """
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)

            return

        headers = dict(scope["headers"])
        raw = headers.get(IAP_USER_HEADER)
        user = iap_user(raw.decode("latin-1") if raw else None)
        token = REQUEST_USER.set(user or os.environ.get(DEV_USER_ENV) or None)

        try:
            await self.app(scope, receive, send)
        finally:
            REQUEST_USER.reset(token)
