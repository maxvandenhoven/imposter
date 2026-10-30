import asyncio
import itertools
from collections.abc import Sequence
from types import SimpleNamespace

import pytest
from conftest import FakeGameSetup, random_players
from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import BaseNode
from google.genai import types
from hypothesis import given, settings
from hypothesis import strategies as st
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from imposter.config import GameConfig, GamePhase, PlayerConfig, SecretWord
from imposter.engine.events import (
    GAME_EVENT_ADAPTER,
    BaseGameEvent,
    GameAbortedEvent,
    PlayerErrorEvent,
    ReflectionEvent,
    SecretWordSaidEvent,
    VoteCastEvent,
)
from imposter.engine.game import Game
from imposter.engine.views import PlayerView
from imposter.orchestration.adk_runner import run_game
from imposter.orchestration.runner import GameRunner
from imposter.orchestration.runner_workflow import (
    REQUEST_STATE_KEY,
    STOPPED_REASON,
    WORKFLOW_NAME,
    GamePhaseNode,
    GameSessions,
    game_workflow,
)
from imposter.orchestration.setup import GameRequest
from imposter.players.base import PlayerProtocol, PlayerResponse, TurnUsage
from imposter.players.fake import RandomPlayer
from imposter.ports.event_bus import InMemoryEventBus
from imposter.ports.game_store import InMemoryGameStore
from imposter.utils.phases import PHASE_TRANSITIONS

MODEL_IDS = ["gemini-flash", "claude-haiku", "gpt-oss", "gemini-flash-lite"]


def new_request(**options: object) -> GameRequest:
    """Build a seeded request for a four-seat game."""
    players = [PlayerConfig(model_id=model_id) for model_id in MODEL_IDS]
    config = GameConfig.model_validate({"players": players, "seed": 5, **options})

    return GameRequest(config=config)


async def play(
    setup: FakeGameSetup, request: GameRequest | None = None
) -> tuple[Game, list[BaseGameEvent]]:
    """Play a game through the workflow and collect every event published on the bus."""
    bus = InMemoryEventBus()
    game = await run_game(
        request=request or new_request(),
        setup=setup,
        bus=bus,
        store=InMemoryGameStore(),
        game_id="game-1",
    )

    return game, [event async for event in bus.subscribe(game_id=game.game_id)]


async def run_session(
    agent: BaseNode, *, sessions: InMemorySessionService, state: dict
) -> list[str]:
    """Run an agent once in the session `game-1` and collect the text of its events."""
    runner = Runner(app=App(name="test", root_agent=agent), session_service=sessions)

    if not await sessions.get_session(app_name="test", user_id="u", session_id="game-1"):
        await sessions.create_session(
            app_name="test", user_id="u", session_id="game-1", state=state
        )

    message = types.Content(role="user", parts=[types.Part(text="Play.")])

    return [
        part.text or ""
        async for event in runner.run_async(
            user_id="u", session_id="game-1", new_message=message
        )
        if event.content and event.content.parts
        for part in event.content.parts
    ]


def without_timestamps(events: Sequence[BaseGameEvent]) -> list[dict]:
    """Dump events for comparison across runs, without the time they were created."""
    return [event.model_dump(exclude={"timestamp"}) for event in events]


def segment_phases(events: Sequence[BaseGameEvent]) -> list[GamePhase]:
    """List the phase of each run of events with the same phase and round, in order."""
    return [
        phase for (phase, _), _ in itertools.groupby(events, lambda e: (e.phase, e.round))
    ]


def workflow_edges() -> set[tuple[str, str, object]]:
    """List the edges of the game workflow as (from node, to node, route)."""
    sessions = GameSessions(
        setup=FakeGameSetup(), bus=InMemoryEventBus(), store=InMemoryGameStore()
    )
    graph = game_workflow(sessions=sessions).graph

    assert graph is not None

    return {(edge.from_node.name, edge.to_node.name, edge.route) for edge in graph.edges}


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


def blundering_players(game: Game) -> list[RandomPlayer]:
    """Seat random players that often say the secret word or vote for themselves."""
    usage = TurnUsage(model_id="random", input_tokens=90, output_tokens=10)

    return [
        RandomPlayer(seed=seat.seat, blunder_rate=0.5, usage=usage) for seat in game.seats
    ]


def test_workflow_edges_are_the_transition_table() -> None:
    edges = workflow_edges()
    transitions = {
        (transition.source.value, transition.target.value, transition.target.value)
        for transition in PHASE_TRANSITIONS
    }

    assert edges == {("__START__", "setup", None), *transitions}


@settings(max_examples=100, deadline=None)
@given(
    clue_rounds=st.integers(min_value=1, max_value=3),
    discussion_rounds=st.integers(min_value=0, max_value=3),
    blunder_rate=st.floats(min_value=0, max_value=0.5),
    token_budget=st.integers(min_value=1_000, max_value=20_000),
    seed=st.integers(),
)
def test_every_transition_of_a_random_game_is_a_workflow_edge(
    clue_rounds: int,
    discussion_rounds: int,
    blunder_rate: float,
    token_budget: int,
    seed: int,
) -> None:
    config = GameConfig(
        players=[PlayerConfig(model_id="model")] * 4,
        clue_rounds=clue_rounds,
        discussion_rounds=discussion_rounds,
        token_budget=token_budget,
        seed=seed,
    )
    game = Game.create(config=config, secret=SecretWord(word="giraffe", category="x"))
    usage = TurnUsage(model_id="random", input_tokens=90, output_tokens=10)
    players = [
        RandomPlayer(seed=seed + seat.seat, blunder_rate=blunder_rate, usage=usage)
        for seat in game.seats
    ]
    asyncio.run(GameRunner(players=players).play(game))
    edges = {(source, target) for source, target, _ in workflow_edges()}
    phases = segment_phases(game.events)

    for source, target in itertools.pairwise(phases):
        assert (source.value, target.value) in edges


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


@pytest.mark.parametrize(
    ("players_for", "options"),
    [
        (random_players, {}),
        (random_players, {"clue_rounds": 3, "discussion_rounds": 0}),
        (blundering_players, {}),
        (random_players, {"token_budget": 500}),
        (random_players, {"token_budget": 3_000}),
    ],
    ids=["default", "no-discussion", "secret-word-said", "abort-in-clue", "abort-late"],
)
async def test_workflow_plays_the_same_game_as_the_game_runner(
    players_for: object, options: dict[str, object]
) -> None:
    request = new_request(**options)
    reference_setup = FakeGameSetup(players_for=players_for)  # ty: ignore[invalid-argument-type]
    reference = await reference_setup.create_game(request=request, game_id="game-1")
    await reference_setup.runner_for(reference).play(reference)
    store = InMemoryGameStore()
    sessions = GameSessions(
        setup=FakeGameSetup(players_for=players_for),  # ty: ignore[invalid-argument-type]
        bus=InMemoryEventBus(),
        store=store,
    )
    state = {REQUEST_STATE_KEY: request.model_dump(mode="json")}

    texts = await run_session(
        game_workflow(sessions=sessions), sessions=InMemorySessionService(), state=state
    )
    game = store.get("game-1")

    assert game is not None
    assert game.is_over
    assert without_timestamps(game.events) == without_timestamps(reference.events)
    assert [GAME_EVENT_ADAPTER.validate_json(text) for text in texts] == list(game.events)


async def test_secret_word_exit_routes_from_the_round_to_the_outcome() -> None:
    game, published = await play(FakeGameSetup(players_for=blundering_players))
    said = game.events_of_type(SecretWordSaidEvent)

    assert said
    assert published == list(game.events)
    assert GamePhase.VOTE not in segment_phases(game.events)
    assert segment_phases(game.events)[-3:] == [
        GamePhase.OUTCOME,
        GamePhase.DEBRIEF,
        GamePhase.DONE,
    ]


async def test_session_of_a_played_game_says_so() -> None:
    sessions = GameSessions(
        setup=FakeGameSetup(), bus=InMemoryEventBus(), store=InMemoryGameStore()
    )
    workflow = game_workflow(sessions=sessions)
    session_service = InMemorySessionService()
    state = {REQUEST_STATE_KEY: new_request().model_dump(mode="json")}

    await run_session(workflow, sessions=session_service, state=state)
    again = await run_session(workflow, sessions=session_service, state=state)

    assert again == ["Game game-1 was already played."]
    assert sessions.active == {}


async def test_workflow_uses_the_default_request_without_one_in_state() -> None:
    store = InMemoryGameStore()
    sessions = GameSessions(
        setup=FakeGameSetup(),
        bus=InMemoryEventBus(),
        store=store,
        default_request=new_request(clue_rounds=1),
    )

    await run_session(
        game_workflow(sessions=sessions), sessions=InMemorySessionService(), state={}
    )
    game = store.get("game-1")

    assert game is not None
    assert game.config.clue_rounds == 1
    assert game.phase is GamePhase.DONE


async def test_workflow_without_any_request_fails() -> None:
    store = InMemoryGameStore()
    sessions = GameSessions(setup=FakeGameSetup(), bus=InMemoryEventBus(), store=store)

    with pytest.raises(ValueError, match="no game request"):
        await run_session(
            game_workflow(sessions=sessions), sessions=InMemorySessionService(), state={}
        )

    assert store.get("game-1") is None


@pytest.fixture(scope="module")
def span_exporter() -> InMemorySpanExporter:
    """Collect the spans of every test in this module in memory."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    return exporter


async def test_workflow_spans_have_a_node_span_per_phase_and_round(
    span_exporter: InMemorySpanExporter,
) -> None:
    span_exporter.clear()
    game, _ = await play(FakeGameSetup())
    spans: tuple[ReadableSpan, ...] = span_exporter.get_finished_spans()
    roots = [span for span in spans if span.parent is None]
    root = roots[0]
    children = sorted(
        (
            span
            for span in spans
            if span.parent and span.parent.span_id == root.context.span_id
        ),
        key=lambda span: span.start_time or 0,
    )

    assert [span.name for span in roots] == [f"invoke_workflow {WORKFLOW_NAME}"]
    assert root.attributes is not None
    assert root.attributes["gen_ai.conversation.id"] == game.game_id
    assert [span.name for span in children] == [
        f"invoke_node {phase}" for phase in segment_phases(game.events)
    ]
    assert all(
        span.attributes and span.attributes["gen_ai.operation.name"] == "invoke_node"
        for span in children
    )


async def test_cancelled_workflow_session_aborts_the_game_and_closes_the_bus() -> None:
    blocking = BlockingPlayer()
    store = InMemoryGameStore()
    bus = InMemoryEventBus()
    setup = FakeGameSetup(players_for=lambda game: [blocking, *random_players(game)[1:]])
    sessions = GameSessions(setup=setup, bus=bus, store=store)
    state = {REQUEST_STATE_KEY: new_request().model_dump(mode="json")}
    task = asyncio.create_task(
        run_session(
            game_workflow(sessions=sessions),
            sessions=InMemorySessionService(),
            state=state,
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
    assert sessions.active == {}


async def test_session_with_every_event_published_has_no_segment() -> None:
    sessions = GameSessions(
        setup=FakeGameSetup(), bus=InMemoryEventBus(), store=InMemoryGameStore()
    )
    session = await sessions.start(
        game_id="game-1", request_data=new_request().model_dump(mode="json")
    )
    session.finish()

    with pytest.raises(RuntimeError, match="Every event of game game-1 is published"):
        _ = session.segment


def test_unknown_game_has_no_session() -> None:
    sessions = GameSessions(
        setup=FakeGameSetup(), bus=InMemoryEventBus(), store=InMemoryGameStore()
    )

    with pytest.raises(KeyError, match="Game game-1 is not being played"):
        sessions.session("game-1")


async def test_node_of_another_phase_aborts_the_game() -> None:
    bus = InMemoryEventBus()
    sessions = GameSessions(setup=FakeGameSetup(), bus=bus, store=InMemoryGameStore())
    session = await sessions.start(
        game_id="game-1", request_data=new_request().model_dump(mode="json")
    )
    node = GamePhaseNode(name="vote", phase=GamePhase.VOTE, sessions=sessions)
    ctx = SimpleNamespace(session=SimpleNamespace(id="game-1"), state={})

    with pytest.raises(RuntimeError, match="Node vote was reached in phase setup"):
        async for _ in node.run_node_impl(ctx=ctx, node_input=None):  # ty: ignore[invalid-argument-type]
            pass

    published = [event async for event in bus.subscribe(game_id="game-1")]

    assert session.game.phase is GamePhase.ABORTED
    assert published == list(session.game.events)
    assert sessions.active == {}
