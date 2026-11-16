import asyncio
import json
import os
from collections.abc import Mapping
from typing import Any, override

import httpx
from google.adk.labs.classifiers import (
    Answer,
    BaseClassifier,
    Binary,
    BinaryAnswer,
    ClassifierInput,
    ClassifierResponse,
    Question,
    RefusalAnswer,
)
from google.adk.models import BaseLlm
from opentelemetry.trace import SpanKind
from pydantic import Field

from imposter.telemetry.spans import TRACER

API_KEY_ENV = "GEMINI_API_KEY"
"""The environment variable with the API key of the Gemini Developer API."""

DECISIONS_MODEL = "gemini-decision-1"
"""The decision model of the Gemini Decisions API."""

DECISIONS_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
"""The base URL of the Gemini Developer API version that serves decisions."""

RETRY_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
"""The HTTP status codes on which a request is sent again."""

RETRY_DELAY_SECONDS = 0.5
"""The wait before the first retry, doubled for each retry after it."""


class GeminiDecisionsClassifier(BaseClassifier):
    """Answers yes or no questions with the Gemini Decisions API.

    The API takes one input and a set of typed questions and returns a calibrated
    probability per question instead of text, in a single fast call. This adapter puts
    it behind ADK's classifier interface, the way ADK's own adapters do for other
    decision APIs. It sends `Binary` questions as the API's `noul` questions and
    supports no other question type, because the judge asks no other.

    The API is part of the Gemini Developer API, not of Vertex AI, so it needs an API
    key instead of Google Cloud credentials. Each call is a client span with the model,
    the token usage and the HTTP status, because the request does not go through ADK
    or the Gen AI SDK, which would trace it.

    Attributes:
        model: The name of the decision model.
        api_key: The API key, read from `GEMINI_API_KEY` when not set.
        base_url: The base URL of the API.
        timeout: The seconds to wait for each request.
        max_attempts: The attempts per call, counting the first.
        http_client: A client to send requests with, a new one per call when not set.
    """

    model: str | BaseLlm = DECISIONS_MODEL
    api_key: str | None = Field(default=None, exclude=True, repr=False)
    base_url: str = DECISIONS_BASE_URL
    timeout: float = 10.0
    max_attempts: int = Field(default=3, ge=1)
    http_client: httpx.AsyncClient | None = Field(default=None, exclude=True, repr=False)

    @override
    async def classify(
        self, *, input: ClassifierInput, questions: Mapping[str, Question]
    ) -> ClassifierResponse:
        """Answer every question against the input in one request.

        Args:
            input: What the questions are about, as text or JSON.
            questions: The yes or no questions, by a name the caller chooses.

        Returns:
            The probability of a yes per question, by the same names. A question the
            API did not answer, for example because a filter blocked the input, gets a
            `RefusalAnswer`.

        Raises:
            ValueError: When there is no API key, the input is not text or JSON, or a
                question is not a `Binary` with instructions.
            RuntimeError: When the API answers with an error.
        """
        model = self.model if isinstance(self.model, str) else self.model.model
        body = {
            "model": f"models/{model}",
            "input": input_text(input),
            "questions": {
                name: noul_question(name=name, question=question)
                for name, question in questions.items()
            },
        }

        with TRACER.start_as_current_span(
            f"decisions {model}",
            kind=SpanKind.CLIENT,
            attributes={
                "gen_ai.operation.name": "decisions",
                "gen_ai.provider.name": "gcp.gemini",
                "gen_ai.request.model": model,
                "server.address": httpx.URL(self.base_url).host,
                "imposter.decisions.question_count": len(questions),
            },
        ) as span:
            if self.http_client is not None:
                response = await self.send(client=self.http_client, body=body)
            else:
                async with httpx.AsyncClient() as client:
                    response = await self.send(client=client, body=body)

            span.set_attribute("http.response.status_code", response.status_code)

            if response.is_error:
                message = (
                    f"The Gemini Decisions API answered with {response.status_code}: "
                    f"{response.text[:500]}"
                )
                raise RuntimeError(message)

            data = response.json()
            usage = data.get("usage") or {}
            span.set_attribute(
                "gen_ai.usage.input_tokens", usage.get("total_input_tokens", 0)
            )

        raw_answers = data.get("answers") or {}

        return ClassifierResponse(
            model_version=model,
            answers={name: binary_answer(raw_answers.get(name)) for name in questions},
        )

    async def send(
        self, *, client: httpx.AsyncClient, body: dict[str, Any]
    ) -> httpx.Response:
        """Post a request, again after a wait when the API is busy or the call fails.

        Args:
            client: The client to send with.
            body: The JSON body of the request.

        Returns:
            The response of the API, which may be an error response.

        Raises:
            ValueError: When there is no API key.
        """
        api_key = self.api_key or os.environ.get(API_KEY_ENV)

        if not api_key:
            message = f"The Gemini Decisions API needs an API key in {API_KEY_ENV}."
            raise ValueError(message)

        async def post() -> httpx.Response:
            return await client.post(
                f"{self.base_url}/decisions",
                json=body,
                headers={"x-goog-api-key": api_key},
                timeout=self.timeout,
            )

        for retry in range(self.max_attempts - 1):
            try:
                response = await post()
            except httpx.TransportError:
                pass
            else:
                if response.status_code not in RETRY_STATUS_CODES:
                    return response

            await asyncio.sleep(RETRY_DELAY_SECONDS * 2**retry)

        # The last attempt is final: its response is returned and its error raised.
        return await post()


def input_text(input: ClassifierInput) -> str:  # noqa: A002
    """Turn the input of a classifier into the text the API takes.

    Args:
        input: Text, or a JSON-ready mapping or sequence.

    Returns:
        The text as it is, or the JSON of anything else.

    Raises:
        ValueError: When the input is multimodal content, which this adapter leaves out.
    """
    if isinstance(input, str):
        return input

    if isinstance(input, (Mapping, list, tuple)):
        return json.dumps(input, ensure_ascii=False)

    message = "The Gemini Decisions adapter takes text or JSON input only."
    raise ValueError(message)


def noul_question(*, name: str, question: Question) -> dict[str, Any]:
    """Turn a `Binary` question into a `noul` question of the API.

    Args:
        name: The name of the question, for the error message.
        question: The question.

    Returns:
        The JSON of the question, with the criteria as the description of a yes.

    Raises:
        ValueError: When the question is not a `Binary` or has no instructions.
    """
    if not isinstance(question, Binary) or question.instructions is None:
        message = f"Question {name!r} must be a Binary question with instructions."
        raise ValueError(message)

    noul: dict[str, Any] = {
        "type": "noul",
        "instructions": input_text(question.instructions),
    }

    if question.criteria is not None:
        noul["criteria"] = {"true_description": input_text(question.criteria)}

    return noul


def binary_answer(raw: Any) -> Answer:
    """Read the answer of the API to one `noul` question.

    Args:
        raw: The JSON of the answer, `None` when the API gave none.

    Returns:
        The probability of a yes with the API's confidence, or a refusal when the
        answer is missing.
    """
    if not isinstance(raw, Mapping) or "noul" not in raw:
        return RefusalAnswer()

    return BinaryAnswer(probability=raw["noul"], confidence=raw.get("confidence"))
