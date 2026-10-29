import asyncio

import pytest

from imposter.utils.retry import call_with_retries, is_transient_error


class StatusError(Exception):
    def __init__(
        self, *, code: int | str | None = None, status_code: int | None = None
    ) -> None:
        super().__init__(f"status {code or status_code}")
        self.code = code
        self.status_code = status_code


class FlakyCall:
    """A call that raises the given errors in order, then returns `"done"`."""

    def __init__(self, errors: list[Exception], *, delay: float = 0.0) -> None:
        self.errors = errors
        self.delay = delay
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        await asyncio.sleep(self.delay)

        if self.errors:
            raise self.errors.pop(0)

        return "done"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError(), True),
        (StatusError(code=429), True),
        (StatusError(status_code=503), True),
        (StatusError(code=408), True),
        (StatusError(code=400), False),
        (StatusError(code="RESOURCE_EXHAUSTED"), True),
        (StatusError(code="RateLimitError"), True),
        (StatusError(code="SAFETY"), False),
        (StatusError(status_code=404), False),
        (ValueError("bad"), False),
    ],
)
def test_is_transient_error(error: Exception, expected: bool) -> None:
    assert is_transient_error(error) is expected


async def test_call_with_retries_retries_transient_errors() -> None:
    call = FlakyCall([StatusError(code=429), StatusError(status_code=500)])

    result = await call_with_retries(
        call, timeout_seconds=1, max_retries=2, backoff_seconds=0
    )

    assert result == "done"
    assert call.calls == 3


async def test_call_with_retries_gives_up_after_the_last_retry() -> None:
    call = FlakyCall([StatusError(code=429)] * 3)

    with pytest.raises(StatusError):
        await call_with_retries(call, timeout_seconds=1, max_retries=2, backoff_seconds=0)

    assert call.calls == 3


async def test_call_with_retries_does_not_retry_other_errors() -> None:
    call = FlakyCall([ValueError("bad request")])

    with pytest.raises(ValueError, match="bad request"):
        await call_with_retries(call, timeout_seconds=1, max_retries=2, backoff_seconds=0)

    assert call.calls == 1


async def test_call_with_retries_times_out_each_attempt() -> None:
    call = FlakyCall([], delay=1)

    with pytest.raises(TimeoutError):
        await call_with_retries(
            call, timeout_seconds=0.01, max_retries=1, backoff_seconds=0
        )

    assert call.calls == 2
