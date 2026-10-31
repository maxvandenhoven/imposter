from contextvars import ContextVar

REQUEST_USER: ContextVar[str | None] = ContextVar("imposter_request_user", default=None)
"""The user of the HTTP request being served, set by the API and read by the trace
plugin, because the ADK run happens inside the request that starts it."""
