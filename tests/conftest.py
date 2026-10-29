"""Fixtures shared by the tests of several packages."""

from collections.abc import AsyncGenerator

import pytest
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types
from pydantic import Field

from imposter.models.catalog import ModelCatalog, ModelCatalogEntry


class ReplayLlm(BaseLlm):
    """An ADK model that replays canned text replies and records every request.

    Attributes:
        replies: The remaining replies, as answer text or an error to raise.
        requests: The requests the model received, in order.
    """

    model: str = "fake"
    replies: list[str | Exception] = Field(default_factory=list)
    requests: list[LlmRequest] = Field(default_factory=list)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse]:
        self.requests.append(llm_request.model_copy(deep=True))
        reply = self.replies.pop(0)

        if isinstance(reply, Exception):
            raise reply

        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=reply)])
        )

    def prompt(self, index: int = -1) -> str:
        """Join the text of the user message of a recorded request."""
        content = self.requests[index].contents[-1]

        return "".join(part.text or "" for part in content.parts or [])


@pytest.fixture(scope="function")
def replay_llm() -> ReplayLlm:
    """A replaying model without replies, to be filled by the test."""
    return ReplayLlm()


@pytest.fixture(scope="session")
def flash_lite() -> ModelCatalogEntry:
    """The catalog entry of Gemini Flash-Lite, the judge and generator model."""
    return ModelCatalog.load().entry("gemini-flash-lite")
