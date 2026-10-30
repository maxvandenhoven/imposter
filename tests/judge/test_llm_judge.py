import json

from conftest import ReplayLlm
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from imposter.judge.llm_judge import LlmJudge
from imposter.models.catalog import ModelCatalogEntry


def reply(*, verdict: bool, confidence: float = 0.9) -> str:
    """Write the JSON answer of the judge model."""
    return json.dumps(
        {"verdict": verdict, "confidence": confidence, "rationale": "Because."}
    )


async def test_obvious_cases_are_decided_without_the_model(
    flash_lite: ModelCatalogEntry, replay_llm: ReplayLlm
) -> None:
    judge = LlmJudge(entry=flash_lite, model=replay_llm)

    same = await judge.is_same_word(guess="Cats", word="cat")
    clue = await judge.is_valid_clue(clue="firefighter", word="fire")

    assert same.verdict is True
    assert clue.verdict is False
    assert replay_llm.requests == []


async def test_undecided_guess_goes_to_the_model(
    flash_lite: ModelCatalogEntry, replay_llm: ReplayLlm
) -> None:
    replay_llm.replies = [reply(verdict=True)]
    judge = LlmJudge(entry=flash_lite, model=replay_llm)

    verdict = await judge.is_same_word(guess="couch", word="sofa")

    assert verdict.verdict is True
    assert verdict.confidence == 0.9
    assert verdict.judge_model == "gemini-flash-lite"
    assert "Guess: couch" in replay_llm.prompt()
    assert replay_llm.requests[0].config.temperature == 0


async def test_undecided_clue_goes_to_the_model(
    flash_lite: ModelCatalogEntry, replay_llm: ReplayLlm
) -> None:
    replay_llm.replies = [reply(verdict=False)]
    judge = LlmJudge(entry=flash_lite, model=replay_llm)

    verdict = await judge.is_valid_clue(clue="couch", word="sofa")

    assert verdict.verdict is False
    assert "Clue: couch" in replay_llm.prompt()


async def test_failing_model_gives_the_lenient_verdict(
    flash_lite: ModelCatalogEntry, replay_llm: ReplayLlm
) -> None:
    replay_llm.replies = [RuntimeError("down"), "not json"]
    judge = LlmJudge(entry=flash_lite, model=replay_llm)

    guess = await judge.is_same_word(guess="couch", word="sofa")
    clue = await judge.is_valid_clue(clue="couch", word="sofa")

    assert (guess.verdict, guess.confidence) == (False, 0.0)
    assert (clue.verdict, clue.confidence) == (True, 0.0)


async def test_each_decision_is_a_judge_span_with_its_verdict(
    flash_lite: ModelCatalogEntry,
    replay_llm: ReplayLlm,
    span_exporter: InMemorySpanExporter,
) -> None:
    span_exporter.clear()
    replay_llm.replies = [reply(verdict=False, confidence=0.7)]
    judge = LlmJudge(entry=flash_lite, model=replay_llm)

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
    assert spans["judge guess"]["gen_ai.request.model"] == "gemini-flash-lite"
