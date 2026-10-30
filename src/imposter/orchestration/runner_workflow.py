from collections.abc import AsyncGenerator
from typing import Any

from google.adk.agents.context import Context
from google.adk.events import Event, EventActions
from google.adk.workflow import START, Edge, Node, Workflow
from google.genai import types
from pydantic import SkipValidation

from imposter.config import GamePhase
from imposter.engine.events import BaseGameEvent
from imposter.engine.game import Game
from imposter.orchestration.runner import GameRunner
from imposter.orchestration.setup import GameRequest, GameSetup
from imposter.ports.event_bus import EventBusProtocol
from imposter.ports.game_store import GameStoreProtocol
from imposter.utils.phases import PHASE_TRANSITIONS, TERMINAL_PHASES

REQUEST_STATE_KEY = "game:request"
"""The session state key of the `GameRequest`, set when the session is created."""

STOPPED_REASON = "the game run stopped early"
"""The abort reason of a game whose run stopped before the game was over, for example
because its task was cancelled or a player raised an unexpected error."""

WORKFLOW_NAME = "game_runner"
"""The ADK name of the game workflow, also the author of its events."""


class GameSession:
    """A game that is played in an ADK session, with its runner and what was published.

    The engine events are published in segments: all events of one phase and round at
    a time, by the workflow node of that phase.

    Attributes:
        game: The game, changed in place as it is played.
        runner: Asks the players and applies their answers to the game.
        bus: Carries the engine events to subscribers.
        published: The number of events already published.
    """

    def __init__(self, *, game: Game, runner: GameRunner, bus: EventBusProtocol) -> None:
        """Initialize the session of a new game, with nothing published yet.

        Args:
            game: The game.
            runner: Asks the players and applies their answers to the game.
            bus: Carries the engine events to subscribers.
        """
        self.game = game
        self.runner = runner
        self.bus = bus
        self.published = 0

    @property
    def segment(self) -> tuple[GamePhase, int | None]:
        """The phase and round of the first event that is not published yet.

        Raises:
            RuntimeError: When every event is published.
        """
        if self.published == len(self.game.events):
            message = f"Every event of game {self.game.game_id} is published."
            raise RuntimeError(message)

        event = self.game.events[self.published]

        return event.phase, event.round

    async def play_segment(self) -> list[BaseGameEvent]:
        """Play the phase and round of the segment and publish its events.

        Phases in which nobody acts, such as the resolution, are played by the engine
        as soon as the phase before them ends, so they only publish.

        Returns:
            The events of the segment, in order.
        """
        segment = self.segment

        while not self.game.is_over and (self.game.phase, self.game.round) == segment:
            await self.runner.play_step(self.game)

        events = [
            event
            for event in self.game.events[self.published :]
            if (event.phase, event.round) == segment
        ]

        return self.publish(len(events))

    def publish(self, count: int | None = None) -> list[BaseGameEvent]:
        """Publish the next events to the bus.

        Args:
            count: How many events to publish, all unpublished ones when not given.

        Returns:
            The published events, in order.
        """
        end = len(self.game.events) if count is None else self.published + count
        events = list(self.game.events[self.published : end])

        for event in events:
            self.bus.publish(game_id=self.game.game_id, event=event)

        self.published = end

        return events

    def finish(self) -> list[BaseGameEvent]:
        """Abort the game when it is not over, publish its last events and close the bus.

        Returns:
            The events published last, in order.
        """
        if not self.game.is_over:
            self.game.abort(STOPPED_REASON)

        events = self.publish()
        self.bus.close(self.game.game_id)

        return events


class GameSessions:
    """The games that the game workflow plays, one per ADK session.

    The session id is the game id. ADK keeps session state and node outputs as JSON, but
    a game, its players and the bus are live objects, so the workflow nodes look them up
    here by session id. The store keeps the games after they end.

    Attributes:
        setup: Creates the games and seats their players.
        bus: Carries the engine events to subscribers.
        store: Keeps the games by id.
        default_request: The request of sessions without one in state, if any.
        active: The sessions of the games being played, by game id.
    """

    def __init__(
        self,
        *,
        setup: GameSetup,
        bus: EventBusProtocol,
        store: GameStoreProtocol,
        default_request: GameRequest | None = None,
    ) -> None:
        """Initialize without games.

        Args:
            setup: Creates the games and seats their players.
            bus: Carries the engine events to subscribers.
            store: Keeps the games by id.
            default_request: The request of sessions without one in state, if any.
        """
        self.setup = setup
        self.bus = bus
        self.store = store
        self.default_request = default_request
        self.active: dict[str, GameSession] = {}

    async def start(
        self, *, game_id: str, request_data: dict[str, Any] | None
    ) -> GameSession:
        """Create a game and seat its players.

        Args:
            game_id: The id of the game, the ADK session id.
            request_data: The `GameRequest` from session state as JSON, if any.

        Returns:
            The session of the new game.

        Raises:
            ValueError: When there is no request and no default either.
        """
        if request_data is not None:
            request = GameRequest.model_validate(request_data)
        elif self.default_request is not None:
            request = self.default_request
        else:
            message = f"The session {game_id} has no game request in its state."
            raise ValueError(message)

        game = await self.setup.create_game(request=request, game_id=game_id)
        self.store.save(game)
        session = GameSession(game=game, runner=self.setup.runner_for(game), bus=self.bus)
        self.active[game_id] = session

        return session

    def session(self, game_id: str) -> GameSession:
        """Get the session of a game being played.

        Args:
            game_id: The id of the game.

        Returns:
            The session.

        Raises:
            KeyError: When the game is not being played.
        """
        if game_id not in self.active:
            message = f"Game {game_id} is not being played."
            raise KeyError(message)

        return self.active[game_id]

    def finish(self, game_id: str) -> list[BaseGameEvent]:
        """Finish a game being played, if it still is, and forget its session.

        Args:
            game_id: The id of the game.

        Returns:
            The events published last, empty when the game was not being played.
        """
        session = self.active.pop(game_id, None)

        return session.finish() if session is not None else []


class GamePhaseNode(Node):
    """The workflow node of one game phase: plays a round of the phase through the engine.

    The node never decides a transition (README D6): it plays the phase and round of
    the next unpublished event through the `GameRunner`, publishes the events of that
    segment, yields each as a content event for `adk web`, and routes to the phase of
    the next event. The setup node creates the game, and the terminal nodes publish the
    last events and close the bus. When the node stops early, for example because its
    task was cancelled, the game is aborted and the bus closed all the same.

    Attributes:
        phase: The phase this node plays.
        sessions: The games being played, by session id.
    """

    phase: GamePhase
    sessions: SkipValidation[GameSessions]

    async def run_node_impl(
        self, *, ctx: Context, node_input: Any
    ) -> AsyncGenerator[Event]:
        """Play the next segment of the session's game and route to the next phase.

        Args:
            ctx: The workflow context of this node run.
            node_input: The output of the node before, unused.

        Yields:
            A content event per engine event, then an event that routes to the phase of
            the next segment, unless the game is over.

        Raises:
            RuntimeError: When the game is not in the phase of this node.
        """
        game_id = ctx.session.id

        if self.phase is GamePhase.SETUP:
            if self.sessions.store.get(game_id) is not None:
                yield text_event(f"Game {game_id} was already played.")
                return

            request_data = ctx.state.get(REQUEST_STATE_KEY)
            session = await self.sessions.start(
                game_id=game_id, request_data=request_data
            )
        else:
            session = self.sessions.session(game_id)

        try:
            phase, _ = session.segment

            if phase is not self.phase:
                message = f"Node {self.name} was reached in phase {phase} of the game."
                raise RuntimeError(message)

            if self.phase in TERMINAL_PHASES:
                events = self.sessions.finish(game_id)
            else:
                events = await session.play_segment()
        except BaseException:
            self.sessions.finish(game_id)
            raise

        for event in events:
            yield text_event(event.model_dump_json())

        if self.phase not in TERMINAL_PHASES:
            next_phase, _ = session.segment
            # The same as `Event(route=...)`, which ty reads as a discarded argument.
            yield Event(actions=EventActions(route=next_phase.value))


def text_event(text: str) -> Event:
    """Build a content event with a text message, as `adk web` shows it.

    Args:
        text: The message.

    Returns:
        The event.
    """
    return Event(content=types.Content(role="model", parts=[types.Part(text=text)]))


def game_workflow(*, sessions: GameSessions, name: str = WORKFLOW_NAME) -> Workflow:
    """Build the ADK workflow that plays a game, with a node per phase.

    The graph is generated from `PHASE_TRANSITIONS`: one edge per transition, routed by
    the name of the phase it enters, so it shows every phase change the engine can make
    and cannot drift from it. Rounds are loop edges.

    Args:
        sessions: The games being played, by session id.
        name: The name of the workflow.

    Returns:
        The workflow, to run with ADK's `Runner` in one session per game.
    """
    nodes = {
        phase: GamePhaseNode(name=phase.value, phase=phase, sessions=sessions)
        for phase in GamePhase
    }
    edges = [
        Edge(from_node=START, to_node=nodes[GamePhase.SETUP]),
        *(
            Edge(
                from_node=nodes[transition.source],
                to_node=nodes[transition.target],
                route=transition.target.value,
            )
            for transition in PHASE_TRANSITIONS
        ),
    ]

    return Workflow(
        name=name,
        description="Plays a game of Imposter between LLM players, one game per session.",
        edges=edges,
    )
