import pytest

from imposter.utils.text import is_single_word
from imposter.words.picker import WordCategory, WordPicker


def test_built_in_categories_hold_30_to_50_unique_single_words() -> None:
    picker = WordPicker.load()

    assert len(picker.categories) >= 10

    for category in picker.categories.values():
        assert 30 <= len(category.words) <= 50, category.name
        assert len(set(category.words)) == len(category.words), category.name
        assert all(is_single_word(word) for word in category.words), category.name


def test_picks_are_deterministic_with_a_seed() -> None:
    first = [WordPicker.load(seed=3).pick() for _ in range(5)]
    second = [WordPicker.load(seed=3).pick() for _ in range(5)]

    assert first == second


def test_pick_avoids_recent_words_until_the_category_is_used_up() -> None:
    category = WordCategory(name="tiny", description="Two words.", words=["echo", "hum"])
    picker = WordPicker(categories=[category], seed=1)

    picks = {picker.pick("tiny")[0] for _ in range(2)}
    third, name = picker.pick("tiny")

    assert picks == {"echo", "hum"}
    assert third in picks
    assert name == "tiny"


def test_unknown_category_is_rejected() -> None:
    with pytest.raises(KeyError, match="no word category named 'nope'"):
        WordPicker.load().pick("nope")
