import pytest

from imposter.judge.checks import clue_check, same_word_check, shared_prefix_length


@pytest.mark.parametrize(
    ("guess", "word", "expected"),
    [
        ("Cats", "cat", True),
        ("cat", "cat", True),
        (" Nostalgia! ", "nostalgia", True),
        ("Butterflies", "butterfly", True),
        ("couch", "sofa", None),
        ("catalogue", "cat", None),
    ],
)
def test_same_word_check(guess: str, word: str, expected: bool | None) -> None:
    verdict = same_word_check(guess=guess, word=word)

    assert (verdict and verdict.verdict) == expected
    assert verdict is None or verdict.judge_model == "code"


@pytest.mark.parametrize(
    ("clue", "word", "expected"),
    [
        ("firefighter", "fire", False),
        ("fire", "firefighter", False),
        ("Echoes", "echo", False),
        ("nostalgic", "nostalgia", False),
        ("jealous", "jealousy", False),
        ("couch", "sofa", None),
        ("melody", "melancholy", None),
        ("at", "cat", None),
        ("photograph", "photon", False),
        ("past", "nostalgia", None),
    ],
)
def test_clue_check(clue: str, word: str, expected: bool | None) -> None:
    verdict = clue_check(clue=clue, word=word)

    assert (None if verdict is None else verdict.verdict) == expected


def test_shared_prefix_length() -> None:
    assert shared_prefix_length("nostalgic", "nostalgia") == 8
    assert shared_prefix_length("abc", "xyz") == 0
