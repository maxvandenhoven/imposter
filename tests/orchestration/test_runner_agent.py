import asyncio

import pytest
from conftest import FakeGameSetup, random_players
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from imposter.config import GameConfig, GamePhase, PlayerConfig
from imposter.engine.events import (
    GAME_EVENT_ADAPTER,
    BaseGameEvent,
    GameAbortedEvent,
    PlayerErrorEvent,
    ReflectionEvent,
    VoteCastEvent,
)
from imposter.engine.game import Game
from imposter.engine.views import PlayerView
from imposter.orchestration.adk_runner import run_game
from imposter.orchestration.runner_agent import (
    REQUEST_STATE_KEY,
    STOPPED_REASON,
    GameRunnerAgent,
)
from imposter.orchestration.setup import GameRequest
from imposter.players.base import PlayerProtocol, PlayerResponse
from imposter.ports.event_bus import InMemoryEventBus
from imposter.ports.game_store import InMemoryGameStore

MODEL_IDS = ["gemini-flash", "claude-haiku", "gpt-oss", "gemini-flash-lite"]


def new_request(**options: object) -> GameRequest:
    """Build a seeded request for a four-seat game."""
    players = [PlayerConfig(model_id=model_id) for model_id in MODEL_IDS]
    config = GameConfig.model_validate({"players": players, "seed": 5, **options})

    return GameRequest(config=config)


async def play(
    setup: FakeGameSetup, request: GameRequest | None = None
) -> tuple[Game, list[BaseGameEvent]]:
    """Play a game through ADK and collect every event published on the bus."""
    bus = InMemoryEventBus()
    game = await run_game(
        request=request or new_request(),
        setup=setup,
        bus=bus,
        store=InMemoryGameStore(),
        game_id="game-1",
    )

    return game, [event async for event in bus.subscribe(game_id=game.game_id)]


class DelayedPlayer:
    """A player that waits before every answer, to make later seats answer first.

    Attributes:
        player: The player that answers.
        delay: The seconds to wait.
    """

    def __init__(self, *, player: PlayerProtocol, delay: float) -> None:
        self.player = player
        self.delay = delay

    async def take_turn(
        self, view: PlayerView, retry_reason: str | None = None
    ) -> PlayerResponse:
        await asyncio.sleep(self.delay)

        return await self.player.take_turn(view=view, retry_reason=retry_reason)


class FailingPlayer:
    """A player whose model always fails."""

    async def take_turn(
        self, view: PlayerView, retry_reason: str | None = None
    ) -> PlayerResponse:
        message = "The model is unavailable."
        raise RuntimeError(message)


class BlockingPlayer:
    """A player that never answers, until its task is cancelled.

    Attributes:
        asked: Set when the player is first asked for a turn.
    """

    def __init__(self) -> None:
        self.asked = asyncio.Event()

    async def take_turn(
        self, view: PlayerView, retry_reason: str | None = None
    ) -> PlayerResponse:
        self.asked.set()
        await asyncio.Event().wait()

        return PlayerResponse(output=None)


async def test_game_runs_to_the_end_and_publishes_every_event() -> None:
    game, published = await play(FakeGameSetup())

    assert game.phase is GamePhase.DONE
    assert published == list(game.events)
    assert [event.seq for event in published] == list(range(len(published)))
    assert len(game.events_of_type(ReflectionEvent)) == len(game.seats)


async def test_parallel_answers_are_applied_in_seat_order() -> None:
    def delayed_players(game: Game) -> list[DelayedPlayer]:
        count = len(game.seats)

        return [
            DelayedPlayer(player=player, delay=(count - seat) / 100)
            for seat, player in enumerate(random_players(game))
        ]

    game, published = await play(FakeGameSetup(players_for=delayed_players))
    votes = [event for event in published if isinstance(event, VoteCastEvent)]
    reflections = [event for event in published if isinstance(event, ReflectionEvent)]

    assert game.phase is GamePhase.DONE
    assert [event.seat for event in votes] == list(range(len(game.seats)))
    assert [event.seat for event in reflections] == list(range(len(game.seats)))


async def test_player_errors_fall_back_and_the_game_goes_on() -> None:
    def players_with_failure(game: Game) -> list[PlayerProtocol]:
        return [FailingPlayer(), *random_players(game)[1:]]

    game, published = await play(FakeGameSetup(players_for=players_with_failure))
    errors = [event for event in published if isinstance(event, PlayerErrorEvent)]

    assert game.phase is GamePhase.DONE
    assert errors
    assert {event.seat for event in errors} == {0}


async def test_game_over_the_token_budget_is_aborted() -> None:
    game, published = await play(FakeGameSetup(), new_request(token_budget=500))

    assert game.phase is GamePhase.ABORTED
    assert isinstance(published[-1], GameAbortedEvent)
    assert "token budget" in published[-1].reason


async def test_cancelled_game_is_aborted_and_the_bus_closed() -> None:
    blocking = BlockingPlayer()
    store = InMemoryGameStore()
    bus = InMemoryEventBus()
    setup = FakeGameSetup(players_for=lambda game: [blocking, *random_players(game)[1:]])
    task = asyncio.create_task(
        run_game(
            request=new_request(), setup=setup, bus=bus, store=store, game_id="game-1"
        )
    )
    await blocking.asked.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    game = store.get("game-1")
    published = [event async for event in bus.subscribe(game_id="game-1")]

    assert game is not None
    assert game.phase is GamePhase.ABORTED
    assert published == list(game.events)
    assert isinstance(published[-1], GameAbortedEvent)
    assert published[-1].reason == STOPPED_REASON


async def run_session(
    agent: GameRunnerAgent, *, sessions: InMemorySessionService, state: dict
) -> list[str]:
    """Run the agent once in the session `game-1` and collect the text of its events."""
    runner = Runner(app_name="test", agent=agent, session_service=sessions)

    if await sessions.get_session(app_name="test", user_id="u", session_id="game-1"):
        session_id = "game-1"
    else:
        session = await sessions.create_session(
            app_name="test", user_id="u", session_id="game-1", state=state
        )
        session_id = session.id

    message = types.Content(role="user", parts=[types.Part(text="Play.")])

    return [
        part.text or ""
        async for event in runner.run_async(
            user_id="u", session_id=session_id, new_message=message
        )
        if event.content and event.content.parts
        for part in event.content.parts
    ]


async def test_agent_yields_every_engine_event_as_adk_event() -> None:
    store = InMemoryGameStore()
    agent = GameRunnerAgent(name="game_runner", setup=FakeGameSetup(), store=store)
    sessions = InMemorySessionService()
    state = {REQUEST_STATE_KEY: new_request().model_dump(mode="json")}

    texts = await run_session(agent, sessions=sessions, state=state)
    game = store.get("game-1")

    assert game is not None
    assert [GAME_EVENT_ADAPTER.validate_json(text) for text in texts] == list(game.events)

    again = await run_session(agent, sessions=sessions, state=state)

    assert again == ["Game game-1 was already played."]


async def test_agent_uses_the_default_request_without_one_in_state() -> None:
    store = InMemoryGameStore()
    agent = GameRunnerAgent(
        name="game_runner",
        setup=FakeGameSetup(),
        store=store,
        default_request=new_request(clue_rounds=1),
    )

    await run_session(agent, sessions=InMemorySessionService(), state={})
    game = store.get("game-1")

    assert game is not None
    assert game.config.clue_rounds == 1
    assert game.phase is GamePhase.DONE


async def test_agent_without_any_request_fails() -> None:
    agent = GameRunnerAgent(name="game_runner", setup=FakeGameSetup())

    with pytest.raises(ValueError, match="no game request"):
        await run_session(agent, sessions=InMemorySessionService(), state={})
