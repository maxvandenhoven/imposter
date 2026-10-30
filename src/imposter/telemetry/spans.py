import hashlib
from collections.abc import Callable, Generator
from contextlib import contextmanager

from google.adk.agents.invocation_context import InvocationContext
from google.adk.plugins import BasePlugin
from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode
from pydantic import BaseModel

from imposter.config import GamePhase
from imposter.engine.events import GameAbortedEvent, UsageEvent
from imposter.engine.game import Game
from imposter.models.catalog import ModelCatalog
from imposter.telemetry.cost import catalog_cost

TRACER = trace.get_tracer("imposter")
"""Opens the spans ADK has no span for: player turns and judge calls."""

RESPONSE_FIELD_CHARS = 200
"""The characters of each response field kept in a span event, so traces stay small."""


class GameTracePlugin(BasePlugin):
    """An ADK plugin that puts the game attributes on the root span of a game run.

    ADK runs the run callbacks of plugins inside its root `invoke_workflow` span, the
    game level of the trace, which the workflow nodes cannot reach. Before the run the
    plugin notes the trace id, and after it, or when the run fails, it sets the game
    attributes from the game in the store. The secret word is only on the span as a
    hash, so trace lists do not spoil it.

    Attributes:
        find_game: Looks a game up by id, which is the ADK session id.
        catalog: The models, for the cost estimate.
        trace_ids: The trace id of each game run so far, by game id.
    """

    def __init__(
        self, *, find_game: Callable[[str], Game | None], catalog: ModelCatalog
    ) -> None:
        """Initialize the plugin without traces.

        Args:
            find_game: Looks a game up by id, which is the ADK session id.
            catalog: The models, for the cost estimate.
        """
        super().__init__(name="game_trace")
        self.find_game = find_game
        self.catalog = catalog
        self.trace_ids: dict[str, int] = {}

    async def before_run_callback(self, *, invocation_context: InvocationContext) -> None:
        """Note the trace id of the run, when tracing is set up.

        Args:
            invocation_context: The ADK context of the run.
        """
        span_context = trace.get_current_span().get_span_context()

        if span_context.is_valid:
            self.trace_ids[invocation_context.session.id] = span_context.trace_id

    async def after_run_callback(self, *, invocation_context: InvocationContext) -> None:
        """Set the game attributes on the root span after the run.

        Args:
            invocation_context: The ADK context of the run.
        """
        self.record_game(invocation_context.session.id)

    async def on_run_error_callback(
        self, *, invocation_context: InvocationContext, error: Exception
    ) -> None:
        """Set the game attributes on the root span when the run fails.

        ADK records the error on the span itself.

        Args:
            invocation_context: The ADK context of the run.
            error: The error, unused.
        """
        self.record_game(invocation_context.session.id)

    def record_game(self, game_id: str) -> None:
        """Set the attributes of a game on the current span, and its status if aborted.

        Args:
            game_id: The id of the game.
        """
        game = self.find_game(game_id)

        if game is None:
            return

        span = trace.get_current_span()
        usages = game.events_of_type(UsageEvent)
        cost = sum(
            catalog_cost(
                catalog=self.catalog,
                model_id=usage.model_id,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                thinking_tokens=usage.thinking_tokens,
            )
            for usage in usages
        )
        word_hash = hashlib.sha256(game.secret.word.encode()).hexdigest()
        span.set_attributes(
            {
                "imposter.game.id": game.game_id,
                "imposter.game.identity_mode": game.config.identity_mode.value,
                "imposter.game.player_count": len(game.seats),
                "imposter.game.imposter_count": game.config.imposter_count,
                "imposter.game.lineup": [seat.player.model_id for seat in game.seats],
                "imposter.game.category": game.secret.category or "",
                "imposter.game.word_sha256": word_hash,
                "imposter.game.outcome": game.outcome.value if game.outcome else "",
                "imposter.game.total_tokens": game.tokens_used,
                "imposter.game.cost_usd": cost,
            }
        )
        aborts = game.events_of_type(GameAbortedEvent)

        if aborts:
            span.set_status(Status(StatusCode.ERROR, aborts[-1].reason))


def mark_phase(*, phase: GamePhase, round_: int | None) -> None:
    """Set the phase attributes on the current span, ADK's `invoke_node` span of a node.

    Args:
        phase: The phase the node plays.
        round_: The round of the phase, if it has rounds.
    """
    span = trace.get_current_span()
    span.set_attribute("imposter.phase.name", phase.value)

    if round_ is not None:
        span.set_attribute("imposter.phase.round", round_)


@contextmanager
def turn_span(*, game: Game, seat: int) -> Generator[Span]:
    """Open the span of one player turn, with the seat and its model.

    ADK has no span per turn: each attempt of a player runs its own nested
    `invoke_workflow`, and this span groups them with the judge calls of the turn.

    Args:
        game: The game.
        seat: The seat whose turn it is.

    Yields:
        The span, current while the turn runs.
    """
    info = game.seats[seat]

    with TRACER.start_as_current_span(
        f"turn {info.name}",
        attributes={
            "imposter.phase.name": game.phase.value,
            "imposter.player.seat": seat,
            "imposter.player.name": info.name,
            "imposter.player.role": info.role.value,
            "gen_ai.request.model": info.player.model_id,
        },
    ) as span:
        yield span


@contextmanager
def judge_span(*, kind: str) -> Generator[Span]:
    """Open the span of one judge decision.

    Most decisions are made by the code checks, which ADK does not see, and ADK's own
    spans of a model call do not carry the verdict.

    Args:
        kind: What is judged, `guess` or `clue`.

    Yields:
        The span, current while the judge decides.
    """
    with TRACER.start_as_current_span(
        f"judge {kind}", attributes={"imposter.judge.kind": kind}
    ) as span:
        yield span


def add_response_event(*, span: Span, response: BaseModel) -> None:
    """Add a structured response to a span as a small event, each field cut short.

    Args:
        span: The span of the turn.
        response: The structured response of the player.
    """
    attributes = {
        f"imposter.response.{name}": str(value)[:RESPONSE_FIELD_CHARS]
        for name, value in response.model_dump().items()
    }
    span.add_event(type(response).__name__, attributes=attributes)
