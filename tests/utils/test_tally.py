from collections import Counter

import pytest

from imposter.config import GameOutcome
from imposter.utils.tally import caught_seats, count_votes, decide_outcome


def test_count_votes_ignores_abstentions() -> None:
    assert count_votes([1, 2, None, 1]) == Counter({1: 2, 2: 1})


@pytest.mark.parametrize(
    ("counts", "catch_count", "expected"),
    [
        ({0: 3, 1: 1}, 1, [0]),
        ({0: 2, 1: 2}, 1, []),
        ({}, 1, []),
        ({0: 3, 1: 2, 2: 2}, 2, [0]),
        ({0: 2, 1: 2, 2: 1}, 2, [0, 1]),
        ({0: 2, 1: 2, 2: 2}, 2, []),
        ({3: 1}, 2, [3]),
        ({0: 0, 1: 1}, 2, [1]),
    ],
)
def test_caught_seats_resolves_boundary_ties_by_catching_nobody(
    counts: dict[int, int], catch_count: int, expected: list[int]
) -> None:
    assert caught_seats(counts=Counter(counts), catch_count=catch_count) == expected


@pytest.mark.parametrize(
    ("caught", "correct_guessers", "expected"),
    [
        ([], [], GameOutcome.IMPOSTER_WINS),
        ([0], [1], GameOutcome.IMPOSTER_WINS),
        ([0, 1], [], GameOutcome.CIVILIANS_WIN),
        ([0, 1], [1], GameOutcome.IMPOSTER_STEALS),
        ([0, 1, 2], [2], GameOutcome.CIVILIANS_WIN),
    ],
)
def test_decide_outcome(
    caught: list[int], correct_guessers: list[int], expected: GameOutcome
) -> None:
    outcome = decide_outcome(
        imposters=[0, 1], caught=caught, correct_guessers=correct_guessers
    )

    assert outcome is expected
