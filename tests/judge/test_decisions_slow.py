"""The Gemini Decisions API for real. Run with `make test-slow`, which loads `.env`."""

import os

import pytest

from imposter.judge.decisions import GeminiDecisionsClassifier
from imposter.judge.judge import Judge

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY"), reason="needs GEMINI_API_KEY"
    ),
]


@pytest.mark.parametrize(
    ("guess", "word", "expected"), [("couch", "sofa", True), ("chair", "sofa", False)]
)
async def test_decisions_api_decides_guesses(
    guess: str, word: str, expected: bool
) -> None:
    judge = Judge(GeminiDecisionsClassifier())

    verdict = await judge.is_same_word(guess=guess, word=word)

    assert verdict.verdict is expected
    assert verdict.confidence > 0


@pytest.mark.parametrize(
    ("clue", "word", "expected"),
    [("yesteryear", "nostalgia", True), ("homesick", "homesickness", False)],
)
async def test_decisions_api_decides_clues(clue: str, word: str, expected: bool) -> None:
    judge = Judge(GeminiDecisionsClassifier())

    verdict = await judge.is_valid_clue(clue=clue, word=word)

    assert verdict.verdict is expected
