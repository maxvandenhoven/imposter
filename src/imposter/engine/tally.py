from collections import Counter
from collections.abc import Iterable


def count_votes(targets: Iterable[int | None]) -> Counter[int]:
    """Count the votes per target seat, ignoring abstentions.

    Args:
        targets: The target seat of every vote, `None` for an abstention.

    Returns:
        The number of votes for each seat that received at least one.
    """
    return Counter(target for target in targets if target is not None)


def caught_seats(counts: Counter[int], catch_count: int) -> list[int]:
    """Select the seats caught by a vote.

    The `catch_count` seats with the most votes are caught. Ties at the boundary catch
    nobody at that rank: a seat is caught only if at most `catch_count` seats have at
    least as many votes. With one imposter this means a tie for the most votes catches
    nobody. Seats without votes are never caught.

    Args:
        counts: The number of votes per seat.
        catch_count: The number of seats to catch, the number of imposters.

    Returns:
        The caught seats, sorted by seat.
    """
    caught = [
        seat
        for seat, votes in counts.items()
        if votes > 0
        and sum(1 for other in counts.values() if other >= votes) <= catch_count
    ]

    return sorted(caught)
