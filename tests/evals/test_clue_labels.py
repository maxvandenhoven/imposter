import pytest
from build_evalsets import ClueLabel, load_labels

from imposter.judge.checks import clue_check
from imposter.utils.text import normalize_word

LABELS = load_labels()


def label_id(label: ClueLabel) -> str:
    return f"{label.word}-{label.clue}"


def test_every_clue_is_labelled() -> None:
    unlabelled = [label_id(label) for label in LABELS if label.legal is None]

    assert LABELS
    assert unlabelled == []


@pytest.mark.parametrize("label", LABELS, ids=label_id)
def test_the_code_checks_agree_with_the_labels(label: ClueLabel) -> None:
    rejected = clue_check(clue=label.clue, word=label.word) is not None

    assert not (rejected and label.legal), "The code checks reject a legal clue."


@pytest.mark.parametrize("label", LABELS, ids=label_id)
def test_a_clue_that_says_the_word_is_labelled_illegal(label: ClueLabel) -> None:
    says_word = normalize_word(label.word) in normalize_word(label.clue)

    assert not (says_word and label.legal), "A clue that says the word is legal."


def test_a_synonym_is_always_legal() -> None:
    illegal_synonyms = [
        label_id(label) for label in LABELS if label.synonym and not label.legal
    ]

    assert illegal_synonyms == []
