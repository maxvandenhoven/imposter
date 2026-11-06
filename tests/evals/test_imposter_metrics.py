import json
from typing import Any

import imposter_metrics
import pytest
from google.adk.evaluation.eval_case import Invocation
from google.adk.evaluation.eval_metrics import EvalMetric, EvalStatus
from google.adk.evaluation.eval_rubrics import Rubric, RubricContent
from google.genai import types
from imposter_metrics import (
    DEBRIEF_WORD_TARGET,
    PLAYER_VIEW_RUBRIC_TYPE,
    SECRET_WORD_RUBRIC_TYPE,
    GuesserAnswer,
    clue_follows_rules,
    clue_keeps_word_hidden,
    clue_passes_judge,
    reflection_brief,
    verdict_match,
    within_word_caps,
    word_kept_secret,
)

from imposter.engine.views import PlayerView
from imposter.judge.base import JudgeVerdict

METRIC = EvalMetric(metric_name="test")


class FakeJudge:
    """A judge that finds every clue valid except the ones it was told to reject.

    Attributes:
        rejected: The clues to reject.
        asked: The clues the judge was asked about, in order.
    """

    def __init__(self, rejected: set[str]) -> None:
        self.rejected = rejected
        self.asked: list[str] = []

    async def is_valid_clue(self, clue: str, word: str) -> JudgeVerdict:
        self.asked.append(clue)

        return JudgeVerdict(
            verdict=clue not in self.rejected,
            confidence=1.0,
            rationale="Scripted.",
            judge_model="fake",
        )


class FakeGuesser:
    """A guesser that names the word once a revealing clue was given.

    Attributes:
        revealing: The clues after which the guesser names the word.
        tasks: The tasks the guesser got, in order.
    """

    def __init__(self, revealing: set[str]) -> None:
        self.revealing = revealing
        self.tasks: list[str] = []

    async def answer(self, task: str) -> GuesserAnswer:
        self.tasks.append(task)
        hit = any(clue in task for clue in self.revealing)

        return GuesserAnswer(guesses=["giraffes" if hit else "zebra", "lion"])


def answer(data: dict[str, Any] | str) -> types.Content:
    text = data if isinstance(data, str) else json.dumps(data)

    return types.Content(role="model", parts=[types.Part(text=text)])


def player_invocation(*, view: PlayerView, response: dict[str, Any]) -> Invocation:
    """An answer to a player turn, with the rubrics that ADK copies from the case."""
    return Invocation(
        user_content=types.Content(role="user", parts=[types.Part(text="Your turn.")]),
        final_response=answer(response),
        rubrics=[
            Rubric(
                rubric_id="player_view",
                rubric_content=RubricContent(text_property=view.model_dump_json()),
                type=PLAYER_VIEW_RUBRIC_TYPE,
            ),
            Rubric(
                rubric_id="secret_word",
                rubric_content=RubricContent(text_property="giraffe"),
                type=SECRET_WORD_RUBRIC_TYPE,
            ),
        ],
    )


async def score(metric: Any, invocation: Invocation) -> float | None:
    result = await metric(METRIC, [invocation], None, None)

    return result.overall_score


@pytest.fixture(scope="function")
def fake_judge(monkeypatch: pytest.MonkeyPatch) -> FakeJudge:
    judge = FakeJudge(rejected={"tower"})
    monkeypatch.setattr(imposter_metrics, "clue_judge", lambda: judge)

    return judge


@pytest.fixture(scope="function")
def fake_guesser(monkeypatch: pytest.MonkeyPatch) -> FakeGuesser:
    guesser = FakeGuesser(revealing={"longneck"})
    monkeypatch.setattr(imposter_metrics, "guesser", lambda: guesser)

    return guesser


@pytest.mark.parametrize(
    ("actual", "passed"),
    [
        ({"verdict": True, "confidence": 0.9, "rationale": "Fine."}, True),
        ({"verdict": False, "confidence": 0.9, "rationale": "Synonym."}, False),
        ("not json", False),
    ],
)
async def test_verdict_match_compares_the_verdict_with_the_label(
    actual: dict[str, Any] | str, passed: bool
) -> None:
    question = types.Content(role="user", parts=[types.Part(text="Clue: thanks")])
    expected = Invocation(user_content=question, final_response=answer({"verdict": True}))
    result = await verdict_match(
        METRIC,
        [Invocation(user_content=question, final_response=answer(actual))],
        [expected],
        None,
    )

    assert result.overall_score == (1.0 if passed else 0.0)
    assert result.overall_eval_status is (
        EvalStatus.PASSED if passed else EvalStatus.FAILED
    )


@pytest.mark.parametrize(
    ("clue", "passed"),
    [("tall", True), ("Neck", False), ("long neck", False), ("babygiraffe", False)],
)
async def test_clue_follows_rules_applies_the_code_rules_only(
    civilian_clue_view: PlayerView, fake_judge: FakeJudge, clue: str, passed: bool
) -> None:
    invocation = player_invocation(view=civilian_clue_view, response={"clue": clue})

    assert await score(clue_follows_rules, invocation) == (1.0 if passed else 0.0)
    assert fake_judge.asked == []


@pytest.mark.parametrize(("clue", "passed"), [("tall", True), ("tower", False)])
async def test_clue_passes_judge_asks_the_production_judge(
    civilian_clue_view: PlayerView, fake_judge: FakeJudge, clue: str, passed: bool
) -> None:
    invocation = player_invocation(view=civilian_clue_view, response={"clue": clue})

    assert await score(clue_passes_judge, invocation) == (1.0 if passed else 0.0)
    assert fake_judge.asked == [clue]


@pytest.mark.parametrize(
    ("response", "passed"),
    [
        ({"clue": "tall"}, True),
        ({"clue": "Giraffes"}, False),
        ({"statement": "Bob's clue was odd."}, True),
        ({"statement": "Clearly a giraffe, Bob."}, False),
        ({"private_reasoning": "No answer."}, False),
    ],
)
async def test_word_kept_secret_uses_the_engine_rules(
    civilian_clue_view: PlayerView, response: dict[str, Any], passed: bool
) -> None:
    invocation = player_invocation(view=civilian_clue_view, response=response)

    assert await score(word_kept_secret, invocation) == (1.0 if passed else 0.0)


@pytest.mark.parametrize(("clue", "passed"), [("tall", True), ("longneck", False)])
async def test_clue_keeps_word_hidden_blames_the_clue_that_gave_the_word_away(
    civilian_clue_view: PlayerView, fake_guesser: FakeGuesser, clue: str, passed: bool
) -> None:
    invocation = player_invocation(view=civilian_clue_view, response={"clue": clue})

    assert await score(clue_keeps_word_hidden, invocation) == (1.0 if passed else 0.0)
    assert "Clues: neck, savanna, spots" in fake_guesser.tasks[0]


async def test_clue_keeps_word_hidden_does_not_blame_a_word_guessed_before(
    civilian_clue_view: PlayerView, fake_guesser: FakeGuesser
) -> None:
    fake_guesser.revealing = {"neck"}
    invocation = player_invocation(view=civilian_clue_view, response={"clue": "tall"})

    assert await score(clue_keeps_word_hidden, invocation) == 1.0
    assert len(fake_guesser.tasks) == 2


@pytest.mark.parametrize(
    ("response", "passed"),
    [
        ({"statement": "word " * 100, "private_reasoning": "word " * 60}, True),
        ({"statement": "word " * 101, "private_reasoning": ""}, False),
        ({"clue": "tall", "private_reasoning": "word " * 61}, False),
    ],
)
async def test_within_word_caps_uses_the_default_caps(
    civilian_clue_view: PlayerView, response: dict[str, Any], passed: bool
) -> None:
    view = civilian_clue_view.model_copy(
        update={
            "rules": civilian_clue_view.rules.model_copy(update={"reasoning_word_cap": 5})
        }
    )
    invocation = player_invocation(view=view, response=response)

    assert await score(within_word_caps, invocation) == (1.0 if passed else 0.0)


@pytest.mark.parametrize(
    ("words", "passed"), [(DEBRIEF_WORD_TARGET, True), (DEBRIEF_WORD_TARGET + 1, False)]
)
async def test_reflection_brief_checks_the_debrief_length(
    civilian_clue_view: PlayerView, words: int, passed: bool
) -> None:
    response = {"reflection": "word " * words}
    invocation = player_invocation(view=civilian_clue_view, response=response)

    assert await score(reflection_brief, invocation) == (1.0 if passed else 0.0)


async def test_a_case_without_a_view_rubric_is_an_error() -> None:
    invocation = Invocation(
        user_content=types.Content(role="user", parts=[types.Part(text="Your turn.")]),
        final_response=answer({"statement": "Hi."}),
    )

    with pytest.raises(ValueError, match="has no PLAYER_VIEW rubric"):
        await score(within_word_caps, invocation)


@pytest.mark.parametrize(
    "text",
    [
        '{"clue": "tall"}',
        '```json\n{"clue": "tall"}\n```',
        '  ```\n{"clue": "tall"}```  ',
    ],
)
def test_response_json_accepts_a_code_fence_like_adk(text: str) -> None:
    assert imposter_metrics.response_json(answer(text)) == {"clue": "tall"}
