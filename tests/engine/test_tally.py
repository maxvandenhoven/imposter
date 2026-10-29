from collections import Counter

import pytest

from imposter.engine.tally import caught_seats, count_votes


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
