import json
from typing import Any

import httpx
import pytest
from google.adk.labs.classifiers import Binary, BinaryAnswer, Choice, RefusalAnswer
from google.genai import types
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from imposter.judge import decisions
from imposter.judge.decisions import GeminiDecisionsClassifier
from imposter.judge.judge import Judge

QUESTION = Binary(instructions="Is it the same word?", criteria="Synonyms count.")


class FakeDecisionsApi:
    """A stand-in for the Gemini Decisions API that replays canned responses.

    Attributes:
        responses: The remaining responses: a status with a JSON body, or an error.
        requests: The requests the API received, in order.
    """

    def __init__(self, responses: list[tuple[int, dict[str, Any]] | Exception]) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Record a request and give the next canned response."""
        self.requests.append(request)
        response = self.responses.pop(0)

        if isinstance(response, Exception):
            raise response

        status, body = response

        return httpx.Response(status, json=body)

    def classifier(self, **options: Any) -> GeminiDecisionsClassifier:
        """Build a classifier that sends its requests to this API."""
        client = httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

        return GeminiDecisionsClassifier(api_key="key", http_client=client, **options)


def answer(noul: float) -> tuple[int, dict[str, Any]]:
    """Write a successful response with one `noul` answer."""
    return 200, {
        "answers": {"same": {"type": "noul", "noul": noul, "confidence": 0.93}},
        "usage": {"total_input_tokens": 42},
    }


@pytest.fixture(scope="function", autouse=True)
def no_retry_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry without waiting."""
    monkeypatch.setattr(decisions, "RETRY_DELAY_SECONDS", 0)


async def test_binary_question_is_sent_as_a_noul_question_with_the_api_key() -> None:
    api = FakeDecisionsApi([answer(0.93)])

    response = await api.classifier().classify(
        input={"secret_word": "sofa", "guess": "couch"}, questions={"same": QUESTION}
    )

    [request] = api.requests
    assert str(request.url) == (
        "https://generativelanguage.googleapis.com/v1beta/decisions"
    )
    assert request.headers["x-goog-api-key"] == "key"
    assert json.loads(request.content) == {
        "model": "models/gemini-decision-1",
        "input": '{"secret_word": "sofa", "guess": "couch"}',
        "questions": {
            "same": {
                "type": "noul",
                "instructions": "Is it the same word?",
                "criteria": {"true_description": "Synonyms count."},
            }
        },
    }
    assert response.answers == {"same": BinaryAnswer(probability=0.93, confidence=0.93)}


async def test_question_without_an_answer_is_a_refusal() -> None:
    api = FakeDecisionsApi([(200, {"prompt_feedback": {"block_reason": "SAFETY"}})])

    response = await api.classifier().classify(input="text", questions={"same": QUESTION})

    assert response.answers == {"same": RefusalAnswer()}


async def test_busy_api_and_failed_calls_are_tried_again() -> None:
    api = FakeDecisionsApi([(429, {}), httpx.ConnectError("reset"), answer(0.2)])

    response = await api.classifier().classify(input="text", questions={"same": QUESTION})

    assert len(api.requests) == 3
    assert response.answers["same"] == BinaryAnswer(probability=0.2, confidence=0.93)


async def test_error_of_the_last_attempt_is_raised() -> None:
    api = FakeDecisionsApi([(503, {}), (503, {"error": "overloaded"})])

    with pytest.raises(RuntimeError, match="503.*overloaded"):
        await api.classifier(max_attempts=2).classify(
            input="text", questions={"same": QUESTION}
        )

    assert len(api.requests) == 2


async def test_client_errors_are_not_tried_again() -> None:
    api = FakeDecisionsApi([(400, {"error": "bad request"})])

    with pytest.raises(RuntimeError, match="400"):
        await api.classifier().classify(input="text", questions={"same": QUESTION})

    assert len(api.requests) == 1


async def test_missing_api_key_other_questions_and_content_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    api = FakeDecisionsApi([])
    choice = Choice(instructions="Which?", criteria={"a": None, "b": None})
    content = types.Content(parts=[types.Part(text="text")])

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        await GeminiDecisionsClassifier().classify(
            input="text", questions={"same": QUESTION}
        )

    with pytest.raises(ValueError, match="Binary question"):
        await api.classifier().classify(input="text", questions={"which": choice})

    with pytest.raises(ValueError, match="text or JSON"):
        await api.classifier().classify(input=content, questions={"same": QUESTION})

    assert api.requests == []


async def test_each_call_is_a_client_span_with_model_tokens_and_status(
    span_exporter: InMemorySpanExporter,
) -> None:
    span_exporter.clear()
    api = FakeDecisionsApi([answer(0.9), (400, {"error": "bad request"})])
    classifier = api.classifier()

    await classifier.classify(input="text", questions={"same": QUESTION})

    with pytest.raises(RuntimeError):
        await classifier.classify(input="text", questions={"same": QUESTION})

    succeeded, failed = span_exporter.get_finished_spans()
    attributes = dict(succeeded.attributes or {})
    assert succeeded.name == "decisions gemini-decision-1"
    assert succeeded.kind is SpanKind.CLIENT
    assert attributes["gen_ai.request.model"] == "gemini-decision-1"
    assert attributes["gen_ai.usage.input_tokens"] == 42
    assert attributes["http.response.status_code"] == 200
    assert attributes["server.address"] == "generativelanguage.googleapis.com"
    assert failed.status.status_code is StatusCode.ERROR
    assert dict(failed.attributes or {})["http.response.status_code"] == 400


async def test_judge_on_the_decisions_api_nests_the_call_in_its_span(
    span_exporter: InMemorySpanExporter,
) -> None:
    span_exporter.clear()
    api = FakeDecisionsApi([(200, {"answers": {"answer": {"noul": 0.97}}})])
    judge = Judge(api.classifier())

    verdict = await judge.is_same_word(guess="couch", word="sofa")

    call, decision = span_exporter.get_finished_spans()
    assert (verdict.verdict, verdict.judge_model) == (True, "gemini-decision-1")
    assert verdict.confidence == pytest.approx(0.97)
    assert decision.name == "judge guess"
    assert call.parent is not None
    assert call.parent.span_id == decision.context.span_id
