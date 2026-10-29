from collections import Counter

from imposter.config import IdentityMode, PlayerConfig

CLASSIC_NAMES = ("Alice", "Bob", "Charlie", "Dave", "Eve", "Frank", "Grace", "Heidi")
"""The classic placeholder names for the `names` identity mode, one per seat up to
`MAX_PLAYERS`, in alphabetical order."""


def seat_names(*, mode: IdentityMode, players: list[PlayerConfig]) -> list[str]:
    """Name the seats of a game under an identity mode.

    In `names` mode the seats get the classic names in alphabetical order, so the name
    also shows the turn order. Seat order is shuffled at setup, so a name reveals nothing
    about the model or role behind it.

    Args:
        mode: The identity mode.
        players: The players in seat order.

    Returns:
        The display name of each seat, in seat order.
    """
    match mode:
        case IdentityMode.SEAT:
            return [f"Player {seat + 1}" for seat in range(len(players))]
        case IdentityMode.NAMES:
            return list(CLASSIC_NAMES[: len(players)])
        case IdentityMode.MODELS:
            labels = [player.model_display_name or player.model_id for player in players]
            totals = Counter(labels)
            seen: Counter[str] = Counter()
            names = []

            for label in labels:
                seen[label] += 1
                names.append(f"{label} #{seen[label]}" if totals[label] > 1 else label)

            return names
