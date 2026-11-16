import json

import pytest
from conftest import ReplayLlm
from google.adk.labs.classifiers import LlmClassifier
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from imposter.judge.decisions import GeminiDecisionsClassifier
from imposter.judge.judge import QUESTION_NAME, Judge


def reply(probability: float) -> str:
    """Write the JSON answer of a model to the one question of the judge."""
    return json.dumps({QUESTION_NAME: {"probability": probability}})


def new_judge(replay_llm: ReplayLlm) -> Judge:
    """Build a judge on ADK's `LlmClassifier` with the replaying model."""
    return Judge(LlmClassifier(model=replay_llm))


async def test_obvious_cases_are_decided_without_the_model(replay_llm: ReplayLlm) -> None:
    judge = new_judge(replay_llm)

    same = await judge.is_same_word(guess="Cats", word="cat")
    clue = await judge.is_valid_clue(clue="firefighter", word="fire")

    assert same.verdict is True
    assert clue.verdict is False
    assert (same.judge_model, clue.judge_model) == ("code", "code")
    assert replay_llm.requests == []


@pytest.mark.parametrize(("probability", "expected"), [(0.9, True), (0.2, False)])
async def test_undecided_guess_is_the_word_when_the_model_says_yes(
    replay_llm: ReplayLlm, probability: float, expected: bool
) -> None:
    replay_llm.replies = [reply(probability)]
    judge = new_judge(replay_llm)

    verdict = await judge.is_same_word(guess="couch", word="sofa")

    assert verdict.verdict is expected
    assert verdict.confidence == pytest.approx(max(probability, 1 - probability))
    assert verdict.judge_model == "fake"
    assert json.loads(replay_llm.prompt()) == {"secret_word": "sofa", "guess": "couch"}
    assert "same thing" in str(replay_llm.requests[0].config.system_instruction)


@pytest.mark.parametrize(("probability", "expected"), [(0.9, False), (0.2, True)])
async def test_undecided_clue_is_invalid_when_the_model_says_yes(
    replay_llm: ReplayLlm, probability: float, expected: bool
) -> None:
    replay_llm.replies = [reply(probability)]
    judge = new_judge(replay_llm)

    verdict = await judge.is_valid_clue(clue="couch", word="sofa")

    assert verdict.verdict is expected
    assert json.loads(replay_llm.prompt()) == {"secret_word": "sofa", "clue": "couch"}
    assert "trivial derivative" in str(replay_llm.requests[0].config.system_instruction)


async def test_threshold_decides_from_which_probability_the_answer_is_yes(
    replay_llm: ReplayLlm,
) -> None:
    replay_llm.replies = [reply(0.6), reply(0.6)]
    strict = Judge(LlmClassifier(model=replay_llm), threshold=0.8)

    lenient_verdict = await new_judge(replay_llm).is_same_word(guess="couch", word="sofa")
    strict_verdict = await strict.is_same_word(guess="couch", word="sofa")

    assert (lenient_verdict.verdict, strict_verdict.verdict) == (True, False)


async def test_failing_model_gives_the_lenient_verdict(replay_llm: ReplayLlm) -> None:
    replay_llm.replies = [RuntimeError("down"), "not json"]
    judge = new_judge(replay_llm)

    guess = await judge.is_same_word(guess="couch", word="sofa")
    clue = await judge.is_valid_clue(clue="couch", word="sofa")

    assert (guess.verdict, guess.confidence) == (False, 0.0)
    assert (clue.verdict, clue.confidence) == (True, 0.0)
    assert "down" in guess.rationale


async def test_each_decision_is_a_judge_span_with_its_verdict(
    replay_llm: ReplayLlm, span_exporter: InMemorySpanExporter
) -> None:
    span_exporter.clear()
    replay_llm.replies = [reply(0.3)]
    judge = new_judge(replay_llm)

    await judge.is_valid_clue(clue="firefighter", word="fire")
    await judge.is_same_word(guess="couch", word="sofa")

    spans = {
        span.name: dict(span.attributes or {})
        for span in span_exporter.get_finished_spans()
        if span.name.startswith("judge ")
    }

    assert spans["judge clue"]["imposter.judge.kind"] == "clue"
    assert spans["judge clue"]["imposter.judge.verdict"] is False
    assert spans["judge clue"]["gen_ai.request.model"] == "code"
    assert spans["judge guess"]["imposter.judge.verdict"] is False
    assert spans["judge guess"]["imposter.judge.confidence"] == 0.7
    assert "0.30" in str(spans["judge guess"]["imposter.judge.rationale"])
    assert spans["judge guess"]["gen_ai.request.model"] == "fake"


def test_judge_uses_the_decisions_api_only_when_its_key_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    without_key = Judge.load()
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    with_key = Judge.load()

    assert isinstance(without_key.classifier, LlmClassifier)
    assert without_key.model_name == "gemini-3.5-flash-lite"
    assert isinstance(with_key.classifier, GeminiDecisionsClassifier)
    assert with_key.model_name == "gemini-decision-1"
