import pytest

from imposter.utils.identity import iap_user


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("accounts.google.com:max@example.com", "max@example.com"),
        ("max@example.com", "max@example.com"),
        ("accounts.google.com:", None),
        ("", None),
        (None, None),
    ],
)
def test_iap_user_strips_the_prefix(header: str | None, expected: str | None) -> None:
    assert iap_user(header) == expected
