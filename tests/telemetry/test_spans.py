import hashlib
from typing import Any

from conftest import FakeGameSetup, ReplayLlm, random_players
from google.adk.agents.context import Context
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from imposter.config import GameConfig, GamePhase, PlayerConfig
from imposter.engine.events import TurnStartedEvent
from imposter.engine.game import Game
from imposter.engine.views import PlayerView
from imposter.models.catalog import ModelCatalog
from imposter.orchestration.adk_runner import run_game
from imposter.orchestration.runner_workflow import WORKFLOW_NAME
from imposter.orchestration.setup import GameRequest
from imposter.players.adk_player import AdkPlayer
from imposter.players.base import PlayerResponse
from imposter.ports.event_bus import InMemoryEventBus
from imposter.ports.game_store import InMemoryGameStore
from imposter.telemetry.spans import GameTracePlugin

MODEL_IDS = ["gemini-flash", "claude-haiku", "gpt-oss", "gemini-flash-lite"]


class FailingPlayer:
    """A player whose model call always raises."""

    async def take_turn(
        self,
        view: PlayerView,
        retry_reason: str | None = None,
        ctx: Context | None = None,
    ) -> PlayerResponse:
        message = "The model is down."
        raise RuntimeError(message)


async def play_traced(
    span_exporter: InMemorySpanExporter,
    setup: FakeGameSetup | None = None,
    **options: object,
) -> tuple[Game, list[ReadableSpan], GameTracePlugin]:
    """Play a seeded four-seat game through the workflow and collect its spans."""
    span_exporter.clear()
    setup = setup or FakeGameSetup()
    players = [PlayerConfig(model_id=model_id) for model_id in MODEL_IDS]
    config = GameConfig.model_validate({"players": players, "seed": 5, **options})
    store = InMemoryGameStore()
    plugin = GameTracePlugin(find_game=store.get)
    game = await run_game(
        request=GameRequest(config=config),
        setup=setup,
        bus=InMemoryEventBus(),
        store=store,
        game_id="game-1",
        trace_plugin=plugin,
    )

    return game, list(span_exporter.get_finished_spans()), plugin


def children(spans: list[ReadableSpan], parent: ReadableSpan) -> list[ReadableSpan]:
    """List the child spans of a span, in start order."""
    return sorted(
        (
            span
            for span in spans
            if span.parent and span.parent.span_id == parent.context.span_id
        ),
        key=lambda span: span.start_time or 0,
    )


def attributes(span: ReadableSpan) -> dict[str, Any]:
    """Get the attributes of a span as a plain dict."""
    return dict(span.attributes or {})


async def test_game_trace_has_game_phase_and_turn_levels(
    span_exporter: InMemorySpanExporter,
) -> None:
    game, spans, plugin = await play_traced(span_exporter)
    [root] = [span for span in spans if span.parent is None]
    game_attributes = attributes(root)
    nodes = children(spans, root)
    turns = [turn for node in nodes for turn in children(spans, node)]
    first_turn = attributes(turns[0])

    assert root.name == f"invoke_workflow {WORKFLOW_NAME}"
    assert plugin.trace_ids == {game.game_id: root.context.trace_id}
    assert game_attributes["imposter.game.id"] == game.game_id
    assert game_attributes["imposter.game.player_count"] == 4
    assert game_attributes["imposter.game.imposter_count"] == 1
    assert game_attributes["imposter.game.identity_mode"] == "names"
    assert game_attributes["imposter.game.lineup"] == tuple(
        seat.player.model_id for seat in game.seats
    )
    assert game_attributes["imposter.game.outcome"] == game.outcome
    assert root.status.status_code is StatusCode.UNSET

    assert all(attributes(node)["imposter.phase.name"] in node.name for node in nodes)
    assert [
        attributes(node)["imposter.phase.round"]
        for node in nodes
        if attributes(node)["imposter.phase.name"] == GamePhase.CLUE
    ] == [1, 2]

    assert all(
        turn.name == f"invoke_node player_{attributes(turn)['imposter.player.seat']}_turn"
        for turn in turns
    )
    assert len(turns) == len(game.events_of_type(TurnStartedEvent))
    assert first_turn["imposter.phase.name"] == GamePhase.CLUE
    assert first_turn["imposter.player.name"] == game.seats[0].name
    assert first_turn["imposter.player.role"] == game.seats[0].role
    assert first_turn["gen_ai.request.model"] == game.seats[0].player.model_id
    assert "gen_ai.usage.input_tokens" not in first_turn
    assert first_turn["imposter.turn.attempts"] >= 1
    assert [event.name for event in turns[0].events] == ["ClueResponse"]


async def test_secret_word_is_only_hashed_on_the_root_span(
    span_exporter: InMemorySpanExporter,
) -> None:
    game, spans, _ = await play_traced(span_exporter)
    [root] = [span for span in spans if span.parent is None]
    values = [str(value).lower() for value in attributes(root).values()]
    word = game.secret.word

    assert attributes(root)["imposter.game.word_sha256"] == (
        hashlib.sha256(word.encode()).hexdigest()
    )
    assert not any(word.lower() in value for value in values)


async def test_failing_player_sets_error_status_on_its_turn(
    span_exporter: InMemorySpanExporter,
) -> None:
    setup = FakeGameSetup(
        players_for=lambda game: [FailingPlayer(), *random_players(game)[1:]]
    )
    _, spans, _ = await play_traced(span_exporter, setup)
    failed = [span for span in spans if attributes(span).get("imposter.player.seat") == 0]

    assert failed
    assert all(span.status.status_code is StatusCode.ERROR for span in failed)
    assert all(attributes(span)["imposter.turn.fallback"] for span in failed)
    assert all([event.name for event in span.events] == ["exception"] for span in failed)


async def test_aborted_game_sets_error_status_on_the_root_span(
    span_exporter: InMemorySpanExporter,
) -> None:
    _, spans, _ = await play_traced(span_exporter, token_budget=150)
    [root] = [span for span in spans if span.parent is None]

    assert root.status.status_code is StatusCode.ERROR
    assert attributes(root)["imposter.game.outcome"] == ""


async def test_player_agent_spans_are_below_the_turn_span(
    span_exporter: InMemorySpanExporter,
) -> None:
    answer = (
        '{"clue": "tall", "statement": "Hm.", "vote_for": "nobody", "guess": "tree", '
        '"reflection": "Fine.", "private_reasoning": "Why not."}'
    )
    model = ReplayLlm(replies=[answer] * 50)
    entry = ModelCatalog.load().entry("gemini-flash")
    setup = FakeGameSetup(
        players_for=lambda game: [
            AdkPlayer(entry=entry, seat=0, model=model),
            *random_players(game)[1:],
        ]
    )
    _, spans, _ = await play_traced(span_exporter, setup)
    turns = [span for span in spans if span.name == "invoke_node player_0_turn"]
    agents = [child for turn in turns for child in children(spans, turn)]
    calls = [call for agent in agents for call in children(spans, agent)]

    assert turns
    assert all(agent.name.startswith("invoke_agent player_0_") for agent in agents)
    assert len(agents) >= len(turns)
    assert calls
    assert all(call.name.startswith("generate_content") for call in calls)
