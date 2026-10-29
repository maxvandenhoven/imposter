from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types
from pydantic import Field, SkipValidation

from imposter.engine.events import BaseGameEvent
from imposter.engine.game import Game
from imposter.orchestration.setup import GameRequest, GameSetup
from imposter.ports.event_bus import EventBusProtocol, InMemoryEventBus
from imposter.ports.game_store import GameStoreProtocol, InMemoryGameStore

REQUEST_STATE_KEY = "game:request"
"""The session state key of the `GameRequest`, set when the session is created."""

STOPPED_REASON = "the game run stopped early"
"""The abort reason of a game whose run stopped before the game was over, for example
because its task was cancelled or a player raised an unexpected error."""


class GameRunnerAgent(BaseAgent):
    """The ADK agent that plays one game per session (README D6, D32).

    It holds no game rules: the `Game` owns them and the `GameRunner` the turn logic.
    The session id is the game id. The first run of a session creates the game from the
    `GameRequest` in session state, or the default request when there is none, as in
    `adk web`. It then plays the game step by step, publishes every new engine event to
    the bus and yields it as an ADK event. When the run stops early, for example because
    its task was cancelled, the game is aborted and the bus closed all the same.

    Attributes:
        setup: Creates the games and seats their players.
        bus: Carries the engine events to subscribers.
        store: Keeps the games by id.
        default_request: The request of sessions without one in state, if any.
    """

    setup: SkipValidation[GameSetup]
    bus: SkipValidation[EventBusProtocol] = Field(default_factory=InMemoryEventBus)
    store: SkipValidation[GameStoreProtocol] = Field(default_factory=InMemoryGameStore)
    default_request: GameRequest | None = None

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event]:
        """Play the game of the session to its end.

        Args:
            ctx: The ADK invocation context.

        Yields:
            An ADK event for every engine event, or a single message when the game of
            the session was already played.

        Raises:
            ValueError: When the session has no request and the agent no default.
        """
        game_id = ctx.session.id

        if self.store.get(game_id) is not None:
            yield self.text_event(ctx=ctx, text=f"Game {game_id} was already played.")
            return

        request_data = ctx.session.state.get(REQUEST_STATE_KEY)

        if request_data is not None:
            request = GameRequest.model_validate(request_data)
        elif self.default_request is not None:
            request = self.default_request
        else:
            message = f"The session {game_id} has no game request in its state."
            raise ValueError(message)

        game = await self.setup.create_game(request=request, game_id=game_id)
        runner = self.setup.runner_for(game)
        self.store.save(game)
        seen = 0

        try:
            while True:
                for event in game.events[seen:]:
                    seen += 1
                    self.bus.publish(game_id=game_id, event=event)
                    yield self.game_event(ctx=ctx, event=event)

                if game.is_over:
                    break

                await runner.play_step(game)
        finally:
            self.finish(game=game, published=seen)

    def finish(self, *, game: Game, published: int) -> None:
        """Abort a game that is not over, publish its last events and close the bus.

        Args:
            game: The game, changed in place when it is not over.
            published: The number of events already published.
        """
        if not game.is_over:
            game.abort(STOPPED_REASON)

        for event in game.events[published:]:
            self.bus.publish(game_id=game.game_id, event=event)

        self.bus.close(game.game_id)

    def game_event(self, *, ctx: InvocationContext, event: BaseGameEvent) -> Event:
        """Wrap an engine event in an ADK event, with the event as JSON text.

        Args:
            ctx: The ADK invocation context.
            event: The engine event.

        Returns:
            The ADK event.
        """
        return self.text_event(ctx=ctx, text=event.model_dump_json())

    def text_event(self, *, ctx: InvocationContext, text: str) -> Event:
        """Build an ADK event with a text message from this agent.

        Args:
            ctx: The ADK invocation context.
            text: The message.

        Returns:
            The ADK event.
        """
        return Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            branch=ctx.branch,
            content=types.Content(role="model", parts=[types.Part(text=text)]),
        )
