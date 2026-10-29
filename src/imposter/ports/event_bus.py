import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

from imposter.engine.events import BaseGameEvent


class EventBusProtocol(Protocol):
    """Carries the events of running games to their subscribers, such as the CLI or SSE.

    The bus buffers every event of a game, so a subscriber that connects late or
    reconnects first gets the events it missed and then the new ones.
    """

    def publish(self, *, game_id: str, event: BaseGameEvent) -> None:
        """Add an event to the end of a game's stream.

        Args:
            game_id: The game.
            event: The next event of the game.
        """
        ...

    def subscribe(
        self, *, game_id: str, from_seq: int = 0
    ) -> AsyncIterator[BaseGameEvent]:
        """Stream the events of a game: the buffered ones first, then new ones.

        Args:
            game_id: The game.
            from_seq: The `seq` of the first event to stream.

        Returns:
            The events in order, ending when the game's stream is closed.
        """
        ...

    def close(self, game_id: str) -> None:
        """End a game's stream, after its last event.

        Args:
            game_id: The game.
        """
        ...


class GameEventStream:
    """The buffered events of one game on the in-memory bus.

    Attributes:
        events: Every event published so far, in order, so the index is the `seq`.
        closed: Whether the stream has ended.
        changed: Set when an event is published or the stream is closed, then replaced.
    """

    def __init__(self) -> None:
        """Initialize an empty, open stream."""
        self.events: list[BaseGameEvent] = []
        self.closed = False
        self.changed = asyncio.Event()

    def notify(self) -> None:
        """Wake every subscriber waiting for a change."""
        self.changed.set()
        self.changed = asyncio.Event()


class InMemoryEventBus:
    """An event bus that keeps every game's events in memory (README D13, D14).

    Attributes:
        streams: The stream of each game, created by the first publish or subscribe.
    """

    def __init__(self) -> None:
        """Initialize an empty bus."""
        self.streams: dict[str, GameEventStream] = {}

    def stream(self, game_id: str) -> GameEventStream:
        """Get the stream of a game, creating it when it is new.

        Args:
            game_id: The game.

        Returns:
            The stream.
        """
        return self.streams.setdefault(game_id, GameEventStream())

    def publish(self, *, game_id: str, event: BaseGameEvent) -> None:
        """Add an event to the end of a game's stream.

        Args:
            game_id: The game.
            event: The next event of the game.

        Raises:
            ValueError: When the stream of the game is closed.
        """
        stream = self.stream(game_id)

        if stream.closed:
            message = f"The event stream of game {game_id} is closed."
            raise ValueError(message)

        stream.events.append(event)
        stream.notify()

    async def subscribe(
        self, *, game_id: str, from_seq: int = 0
    ) -> AsyncIterator[BaseGameEvent]:
        """Stream the events of a game: the buffered ones first, then new ones.

        Args:
            game_id: The game.
            from_seq: The `seq` of the first event to stream.

        Yields:
            The events in order, ending when the game's stream is closed.
        """
        stream = self.stream(game_id)
        seq = from_seq

        while True:
            while seq < len(stream.events):
                yield stream.events[seq]
                seq += 1

            if stream.closed:
                return

            await stream.changed.wait()

    def close(self, game_id: str) -> None:
        """End a game's stream, after its last event.

        Args:
            game_id: The game.
        """
        stream = self.stream(game_id)
        stream.closed = True
        stream.notify()
