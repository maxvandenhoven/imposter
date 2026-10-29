import asyncio
import random
from collections.abc import Awaitable, Callable

TRANSIENT_STATUS_CODES = frozenset({408, 429})
"""HTTP status codes below 500 that are worth retrying: timeout and rate limit."""

TRANSIENT_ERROR_CODES = frozenset(
    {
        "RESOURCE_EXHAUSTED",
        "UNAVAILABLE",
        "INTERNAL",
        "DEADLINE_EXCEEDED",
        "RateLimitError",
        "ServiceUnavailableError",
        "InternalServerError",
        "BadGatewayError",
        "APIConnectionError",
        "Timeout",
        "ServerError",
    }
)
"""Error codes worth retrying when the status number is lost. ADK reports a failed model
call as an error event with the API status (`google-genai`) or the exception class name
(LiteLLM) as code."""


def is_transient_error(error: BaseException) -> bool:
    """Check whether a failed model call is worth retrying.

    Timeouts, rate limits (429) and server errors (5xx) are transient. The status code is
    read from the `code` attribute (`google-genai`) or `status_code` attribute (LiteLLM).
    A code that is a string is looked up in `TRANSIENT_ERROR_CODES`.

    Args:
        error: The error of the call.

    Returns:
        `True` when the call may succeed when it is tried again.
    """
    if isinstance(error, TimeoutError):
        return True

    status = getattr(error, "code", None) or getattr(error, "status_code", None)

    if isinstance(status, str):
        return status in TRANSIENT_ERROR_CODES

    return isinstance(status, int) and (status in TRANSIENT_STATUS_CODES or status >= 500)


async def call_with_retries[ResultT](
    call: Callable[[], Awaitable[ResultT]],
    *,
    timeout_seconds: float,
    max_retries: int,
    backoff_seconds: float,
) -> ResultT:
    """Await a call with a timeout, retrying transient errors with exponential backoff.

    The wait before retry `n` (counting from 0) is `backoff_seconds * 2**n`, times a
    random jitter factor between 1 and 2.

    Args:
        call: Starts the call, once per attempt.
        timeout_seconds: The time limit of each attempt.
        max_retries: The number of retries after the first attempt.
        backoff_seconds: The base wait before the first retry.

    Returns:
        The result of the first attempt that succeeds.

    Raises:
        Exception: The error of the last attempt, or the first error that is not
            transient.
    """
    for attempt in range(max_retries + 1):
        try:
            async with asyncio.timeout(timeout_seconds):
                return await call()
        except Exception as error:
            if attempt == max_retries or not is_transient_error(error):
                raise

        await asyncio.sleep(backoff_seconds * 2**attempt * (1 + random.random()))

    message = "The retry loop ended without a result."
    raise AssertionError(message)
