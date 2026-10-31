IAP_EMAIL_PREFIX = "accounts.google.com:"
"""The prefix IAP puts before the email in `X-Goog-Authenticated-User-Email`."""


def iap_user(header: str | None) -> str | None:
    """Get the email of the signed-in user from the IAP header.

    Args:
        header: The value of `X-Goog-Authenticated-User-Email`, for example
            `accounts.google.com:user@example.com`, or `None` when the header is absent.

    Returns:
        The email without the prefix, or `None` when there is no user in the header.
    """
    if not header:
        return None

    return header.removeprefix(IAP_EMAIL_PREFIX).strip() or None
