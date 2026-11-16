import hashlib
from collections.abc import Generator
from contextlib import contextmanager

from google.adk.agents.invocation_context import InvocationContext
from google.adk.plugins import BasePlugin
from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode
from pydantic import BaseModel

from imposter.engine.events import GameAbortedEvent
from imposter.engine.game import GAME_STATE_KEY, Game, GameSnapshot
from imposter.telemetry.identity import REQUEST_USER

TRACER = trace.get_tracer("imposter")
"""Opens the spans ADK has no span for: player turns and judge calls."""

STOPPED_REASON = "the game run stopped early"
"""The error status of a game whose run stopped before the game was over, for example
because its client went away or a node failed."""

RESPONSE_FIELD_CHARS = 200
"""The characters of each response field kept in a span event, so traces stay small."""


class GameTracePlugin(BasePlugin):
    """An ADK plugin that puts the game attributes on the root span of a game run.

    ADK runs the run callbacks of plugins inside its root `invoke_workflow` span, the
    game level of the trace, which the workflow nodes cannot reach. Before the run the
    plugin notes the trace id, and after it, or when the run fails, it sets the game
    attributes from the game in the state of the session. The secret word is only on
    the span as a hash, so trace lists do not spoil it.

    Attributes:
        trace_ids: The trace id of each game run so far, by game id.
    """

    def __init__(self) -> None:
        """Initialize the plugin without traces."""
        super().__init__(name="game_trace")
        self.trace_ids: dict[str, int] = {}

    async def before_run_callback(self, *, invocation_context: InvocationContext) -> None:
        """Note the trace id of the run and the user who started it.

        The user is the IAP identity of the request, set as `enduser.id` on the root span.

        Args:
            invocation_context: The ADK context of the run.
        """
        span = trace.get_current_span()
        span_context = span.get_span_context()

        if span_context.is_valid:
            self.trace_ids[invocation_context.session.id] = span_context.trace_id

        if user := REQUEST_USER.get():
            span.set_attribute("enduser.id", user)

    async def after_run_callback(self, *, invocation_context: InvocationContext) -> None:
        """Set the game attributes on the root span after the run.

        Args:
            invocation_context: The ADK context of the run.
        """
        self.record_game(invocation_context)

    async def on_run_error_callback(
        self, *, invocation_context: InvocationContext, error: Exception
    ) -> None:
        """Set the game attributes on the root span when the run fails.

        ADK records the error on the span itself.

        Args:
            invocation_context: The ADK context of the run.
            error: The error, unused.
        """
        self.record_game(invocation_context)

    def record_game(self, invocation_context: InvocationContext) -> None:
        """Set the attributes of the session's game on the current span.

        A game that was aborted, or that is not over because the run stopped early,
        sets the error status.

        Args:
            invocation_context: The ADK context of the run.
        """
        snapshot = invocation_context.session.state.get(GAME_STATE_KEY)

        if snapshot is None:
            return

        game = Game.load(GameSnapshot.model_validate(snapshot))
        span = trace.get_current_span()
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
            }
        )
        aborts = game.events_of_type(GameAbortedEvent)

        if aborts:
            span.set_status(Status(StatusCode.ERROR, aborts[-1].reason))
        elif not game.is_over:
            span.set_status(Status(StatusCode.ERROR, STOPPED_REASON))


def mark_turn(*, game: Game, seat: int) -> Span:
    """Set the turn attributes on the current span, ADK's `invoke_node` span of a turn.

    Each turn runs in a run of the `play_turn` node of its own, and the player's agent
    runs as a child node of it, so the span groups the model calls of the turn with its
    judge calls.

    Args:
        game: The game.
        seat: The seat whose turn it is.

    Returns:
        The span of the turn.
    """
    info = game.seats[seat]
    span = trace.get_current_span()
    span.set_attributes(
        {
            "imposter.phase.name": game.phase.value,
            "imposter.phase.round": game.round or 0,
            "imposter.player.seat": seat,
            "imposter.player.name": info.name,
            "imposter.player.role": info.role.value,
            "gen_ai.request.model": info.player.model_id,
        }
    )

    return span


def record_turn(
    *,
    span: Span,
    attempts: int,
    response: BaseModel | None,
    problems: list[str],
    truncated: bool,
) -> None:
    """Set the outcome of a turn on its span: retries, fallback and errors.

    The tokens of each model call are already on ADK's `generate_content` spans below
    the turn, so they are not repeated here.

    Args:
        span: The span of the turn.
        attempts: How many times the player was asked.
        response: The last structured response of the player, if any.
        problems: What went wrong, empty when the response was accepted.
        truncated: Whether the game cuts the statement or reasoning to the cap.
    """
    span.set_attributes(
        {
            "imposter.turn.attempts": attempts,
            "imposter.turn.fallback": response is None or bool(problems),
            "imposter.turn.truncated": truncated,
        }
    )

    if response is not None:
        attributes = {
            f"imposter.response.{name}": str(value)[:RESPONSE_FIELD_CHARS]
            for name, value in response.model_dump().items()
        }
        span.add_event(type(response).__name__, attributes=attributes)

    if problems:
        span.set_status(Status(StatusCode.ERROR, " | ".join(problems)))


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
