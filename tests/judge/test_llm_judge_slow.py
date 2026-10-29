"""The judge against Vertex AI. Run with `make test-slow`, which loads `.env`."""

import os

import pytest

from imposter.judge.llm_judge import LlmJudge

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("GOOGLE_CLOUD_PROJECT"), reason="needs GOOGLE_CLOUD_PROJECT"
    ),
]


@pytest.mark.parametrize(
    ("guess", "word", "expected"), [("couch", "sofa", True), ("chair", "sofa", False)]
)
async def test_real_judge_decides_guesses(guess: str, word: str, expected: bool) -> None:
    verdict = await LlmJudge().is_same_word(guess=guess, word=word)

    assert verdict.verdict is expected
    assert verdict.confidence > 0


@pytest.mark.parametrize(
    ("clue", "word", "expected"),
    [("yesteryear", "nostalgia", True), ("homesick", "homesickness", False)],
)
async def test_real_judge_decides_clues(clue: str, word: str, expected: bool) -> None:
    verdict = await LlmJudge().is_valid_clue(clue=clue, word=word)

    assert verdict.verdict is expected
