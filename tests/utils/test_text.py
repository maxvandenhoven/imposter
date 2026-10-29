import pytest

from imposter.utils.text import (
    clean_word,
    is_single_word,
    mentions_word,
    normalize_word,
    truncate_words,
)


@pytest.mark.parametrize(
    ("text", "expected"), [("  Bark. ", "Bark"), ('"fur"', "fur"), ("why?!", "why")]
)
def test_clean_word_strips_whitespace_and_punctuation(text: str, expected: str) -> None:
    assert clean_word(text) == expected


@pytest.mark.parametrize("text", ["bark", "x-ray", "rock'n", "R2D2", "café"])
def test_is_single_word_accepts_one_word(text: str) -> None:
    assert is_single_word(text)


@pytest.mark.parametrize("text", ["", "two words", "-dash", "end-", "a_b", "a/b"])
def test_is_single_word_rejects_everything_else(text: str) -> None:
    assert not is_single_word(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Giraffes", "giraffe"),
        ("cherries", "cherry"),
        ("boxes", "box"),
        ("churches", "church"),
        ("glass", "glass"),
        ("bus", "bus"),
        (" Apple! ", "apple"),
    ],
)
def test_normalize_word_lowercases_and_singularises(text: str, expected: str) -> None:
    assert normalize_word(text) == expected


def test_truncate_words_keeps_short_text() -> None:
    assert truncate_words("  one two three ", cap=3) == ("one two three", False)


def test_truncate_words_cuts_long_text() -> None:
    assert truncate_words("one two\nthree four", cap=2) == ("one two", True)


@pytest.mark.parametrize(
    ("text", "word", "expected"),
    [
        ("It has a CHERRY on top.", "cherry", True),
        ("Two cherries, please.", "cherry", True),
        ("Cherrys everywhere", "cherry", True),
        ("A cherrystone clam.", "cherry", False),
        ("Pick a category.", "cat", False),
        ("No fruit here.", "cherry", False),
    ],
)
def test_mentions_word_matches_whole_words_and_plurals(
    text: str, word: str, expected: bool
) -> None:
    assert mentions_word(text=text, word=word) is expected
