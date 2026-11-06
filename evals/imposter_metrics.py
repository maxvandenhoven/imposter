"""Custom ADK eval metrics of the Imposter evals.

ADK imports these functions by name from the `custom_metrics` of a `*.test_config.json`
(`code_config.name`, for example `imposter_metrics.verdict_match`), so `evals/` must be
on the import path (`PYTHONPATH=evals`, which the `make eval-*` targets set). ADK hides
the threshold of a custom metric from it, so each metric decides itself whether a case
passed: every metric here is a yes-or-no check that passes at score 1.

A metric gets only the invocations of a case, not its session state. Player cases
therefore carry their `PlayerView` and the secret word a second time, as rubrics of the
types `PLAYER_VIEW` and `SECRET_WORD`, which no built-in metric grades and ADK copies
onto every actual invocation.

The player metrics are split by what they depend on, so that a change to the judge and
a change to the players can be told apart (`docs/plans/evaluation.md`): only
`clue_passes_judge` asks the production judge. `clue_keeps_word_hidden` asks a fixed
guesser model that is not part of the game.
"""

import functools
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from google.adk.evaluation.eval_case import ConversationScenario, Invocation
from google.adk.evaluation.eval_metrics import EvalMetric, EvalStatus
from google.adk.evaluation.evaluator import EvaluationResult, PerInvocationResult
from google.genai import types
from player_turn import case_view
from pydantic import BaseModel, Field

from imposter.engine.views import PlayerView
from imposter.judge.llm_judge import LlmJudge
from imposter.models.catalog import ModelCatalog
from imposter.models.structured import StructuredTaskAgent
from imposter.utils.text import clean_word, is_single_word, mentions_word, normalize_word

PLAYER_VIEW_RUBRIC_TYPE = "PLAYER_VIEW"
"""The rubric type that carries the view of a player case to the metrics."""

SECRET_WORD_RUBRIC_TYPE = "SECRET_WORD"
"""The rubric type that carries the secret word of a player case to the metrics."""

DEBRIEF_WORD_TARGET = 80
"""The most words a debrief reflection should have."""

GUESSER_MODEL_ID = "gemini-flash"
"""The catalog id of the model that tries to guess the word from the clues."""

GUESSER_GUESSES = 3
"""How many guesses the guesser makes."""

GUESSER_INSTRUCTION = """\
You are an expert player of a word game. Players know a secret word and give one-word
clues about it. From the clues alone, guess the secret word."""

GUESSER_TASK = """\
Clues: {clues}

Give your {count} best guesses at the secret word, one word each, the most likely
first."""

type InvocationCheck = Callable[[Invocation, Invocation | None], Awaitable[bool]]
"""A check of one actual invocation and its expected invocation, if any."""

logger = logging.getLogger(__name__)


class GuesserAnswer(BaseModel):
    """The structured answer of the guesser model.

    Attributes:
        guesses: The guesses at the secret word, the most likely first.
    """

    guesses: list[str] = Field(max_length=GUESSER_GUESSES)


@functools.cache
def clue_judge() -> LlmJudge:
    """Return the production judge, built on first use so importing needs no credentials.

    Returns:
        The judge.
    """
    return LlmJudge()


@functools.cache
def guesser() -> StructuredTaskAgent[GuesserAnswer]:
    """Return the guesser, built on first use.

    Returns:
        The guesser agent, at temperature 0.
    """
    return StructuredTaskAgent(
        name="guesser",
        entry=ModelCatalog.load().entry(GUESSER_MODEL_ID),
        instruction=GUESSER_INSTRUCTION,
        response_type=GuesserAnswer,
        max_output_tokens=200,
        temperature=0,
    )


def response_json(content: types.Content | None) -> dict[str, Any]:
    """Parse the JSON answer in a final response.

    Args:
        content: The final response.

    Returns:
        The parsed object, empty when the response is missing or not a JSON object.
    """
    text = "".join(part.text or "" for part in content.parts or []) if content else ""
    text = text.strip()

    # Like ADK's output schema validation, accept JSON wrapped in a Markdown code fence,
    # which models without native structured output such as Mistral often send.
    if len(text) >= 6 and text.startswith("```") and text.endswith("```"):
        text = text[3:-3].removeprefix("json").strip()

    try:
        answer = json.loads(text)
    except json.JSONDecodeError:
        return {}

    return answer if isinstance(answer, dict) else {}


def rubric_text(*, invocation: Invocation, rubric_type: str) -> str:
    """Read the text of the rubric of one type that ADK copied from the case.

    Args:
        invocation: An actual invocation.
        rubric_type: The rubric type.

    Returns:
        The text.

    Raises:
        ValueError: When the case has no rubric of the type.
    """
    for rubric in invocation.rubrics or []:
        if rubric.type == rubric_type and rubric.rubric_content.text_property:
            return rubric.rubric_content.text_property

    message = f"Invocation {invocation.invocation_id} has no {rubric_type} rubric."
    raise ValueError(message)


def player_view(invocation: Invocation) -> PlayerView:
    """Read the view of a player case, with the current default caps.

    Args:
        invocation: An actual invocation.

    Returns:
        The view.
    """
    text = rubric_text(invocation=invocation, rubric_type=PLAYER_VIEW_RUBRIC_TYPE)

    return case_view(PlayerView.model_validate_json(text))


def secret_word(invocation: Invocation) -> str:
    """Read the secret word of a player case, also known for imposters.

    Args:
        invocation: An actual invocation.

    Returns:
        The secret word.
    """
    return rubric_text(invocation=invocation, rubric_type=SECRET_WORD_RUBRIC_TYPE)


def answer_text(*, invocation: Invocation, field: str) -> str | None:
    """Read one text field of a player's answer.

    Args:
        invocation: An actual invocation.
        field: The field, such as `clue`.

    Returns:
        The text, or `None` when the answer has no such non-empty field.
    """
    value = response_json(invocation.final_response).get(field)

    return value if isinstance(value, str) and value.strip() else None


def word_count(text: str | None) -> int:
    """Count the words of a text.

    Args:
        text: The text, if any.

    Returns:
        The number of words separated by whitespace.
    """
    return len(text.split()) if text else 0


async def pass_fail_result(
    *,
    actual_invocations: list[Invocation],
    expected_invocations: list[Invocation] | None,
    passes: InvocationCheck,
) -> EvaluationResult:
    """Score each invocation 1 or 0 with a check, and pass the case when all pass.

    Args:
        actual_invocations: The invocations of the agent under test.
        expected_invocations: The invocations of the eval case, if any.
        passes: The check of one actual invocation and its expected invocation.

    Returns:
        The result, with the share of passing invocations as the overall score.
    """
    expected = expected_invocations or [None] * len(actual_invocations)
    results = []

    for actual, wanted in zip(actual_invocations, expected, strict=True):
        passed = await passes(actual, wanted)
        results.append(
            PerInvocationResult(
                actual_invocation=actual,
                expected_invocation=wanted,
                score=1.0 if passed else 0.0,
                eval_status=EvalStatus.PASSED if passed else EvalStatus.FAILED,
            )
        )

    scores = [result.score or 0.0 for result in results]

    return EvaluationResult(
        overall_score=sum(scores) / len(scores) if scores else None,
        overall_eval_status=(
            EvalStatus.PASSED
            if all(score == 1.0 for score in scores)
            else EvalStatus.FAILED
        ),
        per_invocation_results=results,
    )


def invocation_metric(passes: InvocationCheck) -> Callable[..., Awaitable[Any]]:
    """Turn a check of one invocation into an ADK custom metric function.

    Args:
        passes: The check of one actual invocation and its expected invocation.

    Returns:
        The metric function, with the signature ADK calls custom metrics with.
    """

    @functools.wraps(passes)
    async def metric(
        eval_metric: EvalMetric,
        actual_invocations: list[Invocation],
        expected_invocations: list[Invocation] | None,
        conversation_scenario: ConversationScenario | None,
    ) -> EvaluationResult:
        return await pass_fail_result(
            actual_invocations=actual_invocations,
            expected_invocations=expected_invocations,
            passes=passes,
        )

    return metric


@invocation_metric
async def verdict_match(actual: Invocation, expected: Invocation | None) -> bool:
    """Check that the judge's verdict equals the labelled verdict of the case.

    Args:
        actual: The judge's answer, JSON with a `verdict`.
        expected: The labelled answer, JSON with a `verdict`.

    Returns:
        Whether the verdicts match.
    """
    wanted = response_json(expected.final_response if expected else None)
    verdict = response_json(actual.final_response).get("verdict")

    return isinstance(verdict, bool) and verdict == wanted.get("verdict")


@invocation_metric
async def clue_follows_rules(actual: Invocation, expected: Invocation | None) -> bool:
    """Check a clue against the code rules of a clue turn, without the judge.

    The clue must be one word, not given before (`Game.clue_rejection`) and must not say
    the secret word. This metric depends on the player only.

    Args:
        actual: The player's answer, JSON with a `clue`.
        expected: Unused, the cases have no expected answer.

    Returns:
        Whether the clue follows the rules.
    """
    clue = answer_text(invocation=actual, field="clue")
    view = player_view(actual)
    given = {normalize_word(earlier.clue) for earlier in view.clues if earlier.clue}

    return (
        clue is not None
        and is_single_word(clean_word(clue))
        and normalize_word(clue) not in given
        and normalize_word(secret_word(actual)) not in normalize_word(clue)
    )


@invocation_metric
async def clue_passes_judge(actual: Invocation, expected: Invocation | None) -> bool:
    """Check that the production judge accepts a clue: its code checks, then its model.

    This metric depends on both the player and the judge. Compare it with
    `clue_follows_rules` and the judge eval to tell which of the two changed.

    Args:
        actual: The player's answer, JSON with a `clue`.
        expected: Unused, the cases have no expected answer.

    Returns:
        Whether the judge finds the clue valid.
    """
    clue = answer_text(invocation=actual, field="clue")

    if clue is None:
        return False

    verdict = await clue_judge().is_valid_clue(clue=clue, word=secret_word(actual))

    return verdict.verdict


@invocation_metric
async def word_kept_secret(actual: Invocation, expected: Invocation | None) -> bool:
    """Check that a clue or statement does not say the secret word, by the engine's rules.

    A clue says the word when it contains it after normalisation (`Game.clue_says_word`),
    a statement when it mentions it as a whole word or simple plural
    (`Game.statement_says_word`). Either ends the game and loses it for the speaker's
    side. An answer without a clue or statement fails.

    Args:
        actual: The player's answer, JSON with a `clue` or a `statement`.
        expected: Unused, the cases have no expected answer.

    Returns:
        Whether the word stayed secret.
    """
    word = secret_word(actual)
    clue = answer_text(invocation=actual, field="clue")
    statement = answer_text(invocation=actual, field="statement")

    if clue is not None:
        return normalize_word(word) not in normalize_word(clue)

    return statement is not None and not mentions_word(text=statement, word=word)


async def guessed(*, clues: list[str], word: str) -> bool:
    """Ask the guesser whether the word is among its guesses from the clues.

    Args:
        clues: The clues, in order.
        word: The secret word.

    Returns:
        Whether a guess is the word after normalisation, `False` without clues or when
        the guesser fails.
    """
    if not clues:
        return False

    task = GUESSER_TASK.format(clues=", ".join(clues), count=GUESSER_GUESSES)

    try:
        answer = await guesser().answer(task)
    except RuntimeError:
        logger.warning("The guesser gave no answer for the clues %s.", clues)
        return False

    return normalize_word(word) in {normalize_word(guess) for guess in answer.guesses}


@invocation_metric
async def clue_keeps_word_hidden(actual: Invocation, expected: Invocation | None) -> bool:
    """Check that a clue does not make the word guessable from the clues.

    A guesser model gets the clues given so far and makes three guesses, once without and
    once with the new clue. The clue fails when the word is among the guesses only with
    it, so a word that was already guessable is not blamed on the clue.

    Args:
        actual: The player's answer, JSON with a `clue`.
        expected: Unused, the cases have no expected answer.

    Returns:
        Whether the word stayed hidden after the clue.
    """
    clue = answer_text(invocation=actual, field="clue")

    if clue is None:
        return False

    word = secret_word(actual)
    earlier = [given.clue for given in player_view(actual).clues if given.clue]

    if not await guessed(clues=[*earlier, clue], word=word):
        return True

    return await guessed(clues=earlier, word=word)


@invocation_metric
async def within_word_caps(actual: Invocation, expected: Invocation | None) -> bool:
    """Check that a statement and the private reasoning keep to the word caps.

    The game cuts longer texts, so this measures whether the player follows the caps
    the prompt states. The caps are the current defaults of `GameConfig`.

    Args:
        actual: The player's answer.
        expected: Unused, the cases have no expected answer.

    Returns:
        Whether every capped field is within its cap.
    """
    rules = player_view(actual).rules
    statement = answer_text(invocation=actual, field="statement")
    reasoning = answer_text(invocation=actual, field="private_reasoning")

    return (
        word_count(statement) <= rules.statement_word_cap
        and word_count(reasoning) <= rules.reasoning_word_cap
    )


@invocation_metric
async def reflection_brief(actual: Invocation, expected: Invocation | None) -> bool:
    """Check that a debrief reflection has at most `DEBRIEF_WORD_TARGET` words.

    Args:
        actual: The player's answer, JSON with a `reflection`.
        expected: Unused, the cases have no expected answer.

    Returns:
        Whether the reflection is present and brief.
    """
    reflection = answer_text(invocation=actual, field="reflection")

    return reflection is not None and word_count(reflection) <= DEBRIEF_WORD_TARGET
