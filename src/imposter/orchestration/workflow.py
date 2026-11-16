from collections.abc import AsyncGenerator, Generator
from typing import Self

from google.adk.agents.context import Context
from google.adk.events import Event, EventActions
from google.adk.workflow import START, Edge, Workflow, node
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from imposter.config import GameConfig, GamePhase, PlayerRole
from imposter.engine.events import BaseGameEvent
from imposter.engine.game import GAME_STATE_KEY, ActionRejection, Game, GameSnapshot
from imposter.engine.responses import ClueResponse, GuessResponse, PhaseResponse
from imposter.judge.base import JudgeVerdict
from imposter.judge.checks import clue_check
from imposter.judge.judge import Judge
from imposter.models.catalog import ModelCatalog
from imposter.orchestration.setup import DEFAULT_MODEL_IDS, GameRequest
from imposter.players.base import PlayerSeatingProtocol, TurnUsage
from imposter.players.llm_player import LlmPlayerSeating
from imposter.telemetry.spans import mark_turn, record_turn
from imposter.words.generator import WordGenerator
from imposter.words.options import SecretWordResolver
from imposter.words.picker import WordPicker

REQUEST_STATE_KEY = "game:request"
"""The session state key of the `GameRequest`, set when the session is created."""

WORKFLOW_NAME = "game_runner"
"""The ADK name of the game workflow, also the author of its events."""

GAME_EVENT_METADATA_KEY = "game_event"
"""The key of the engine event, as JSON, in the custom metadata of its ADK event."""

TURN_ROUTE = "turn"
"""The route from `next_turns` to `play_turn`, taken as long as the game is not over."""

OVER_ROUTE = "over"
"""The route from `next_turns` to `finish`, taken when the game is done or aborted."""

MAX_ATTEMPTS = 2
"""Attempts per turn: the first answer plus one retry with the rejection reason."""


class TurnResult(BaseModel):
    """What a player answered in one turn, ready to apply to the game.

    Attributes:
        seat: The seat that took the turn.
        response: The last response of the player, `None` when it gave none.
        rejection: Why the last response was rejected, `None` when it was accepted.
        guess_verdict: The judge's verdict on an inexact guess, if one was asked.
        usages: The tokens every model call of the turn used.
        errors: What went wrong during the turn, for `player_error` events.
        attempts: How many times the player was asked.
    """

    model_config = ConfigDict(frozen=True)

    seat: int
    response: PhaseResponse | None = None
    rejection: ActionRejection | None = None
    guess_verdict: JudgeVerdict | None = None
    usages: list[TurnUsage] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    attempts: int = 0


class GameWorkflowBuilder:
    """Builds the ADK workflow that plays a game, out of five function nodes.

    The graph is a loop: `setup` creates the game, `next_turns` starts the next turn or
    all turns of a parallel phase, `play_turn` asks one player per started turn and
    `apply_turns` applies the answers, until `next_turns` finds the game over and
    routes to `finish`. The engine decides everything: which seats act,
    what each seat may see, whether an answer is valid and when the game is over
    (README D6). The nodes only move data between the engine, the players and ADK.

    The game lives in session state as a snapshot (`GAME_STATE_KEY`). Each node loads
    it, and the nodes that change it save it back and yield an ADK event per new engine
    event. Asking is the only step that does I/O, and it never changes the game, so
    the turns of a parallel phase run against the same game and their answers are
    applied in seat order.

    Attributes:
        words: Chooses the secret word of a new game.
        players: Decides who plays each seat.
        judge: Decides whether a clue that passed the code checks is valid, when the
            game's `model_clue_check` is on, and whether a guess that is not an exact
            match is the word, if set.
        default_request: The request of sessions without one in state, if any.
    """

    def __init__(
        self,
        *,
        words: SecretWordResolver,
        players: PlayerSeatingProtocol,
        judge: Judge | None = None,
        default_request: GameRequest | None = None,
    ) -> None:
        """Initialize the builder.

        Args:
            words: Chooses the secret word of a new game.
            players: Decides who plays each seat.
            judge: Judges clues and guesses, if set.
            default_request: The request of sessions without one in state, if any.
        """
        self.words = words
        self.players = players
        self.judge = judge
        self.default_request = default_request

    @classmethod
    def load(cls, *, seed: int | None = None, with_default_request: bool = False) -> Self:
        """Build the builder with the built-in catalog and words, and models as players.

        Args:
            seed: An optional seed for reproducible random words.
            with_default_request: Whether sessions without a request play a default
                game, as `adk web` needs.

        Returns:
            The builder.
        """
        catalog = ModelCatalog.load()
        words = SecretWordResolver(
            picker=WordPicker.load(seed=seed), generator=WordGenerator()
        )
        default_request = None

        if with_default_request:
            players = catalog.player_configs(DEFAULT_MODEL_IDS)
            default_request = GameRequest(config=GameConfig(players=players))

        return cls(
            words=words,
            players=LlmPlayerSeating(catalog),
            judge=Judge.load(),
            default_request=default_request,
        )

    def build(self, name: str = WORKFLOW_NAME) -> Workflow:
        """Build the workflow.

        Args:
            name: The name of the workflow.

        Returns:
            The workflow, to run with ADK's `Runner` in one session per game.
        """
        # Nodes that run child nodes with `ctx.run_node` must rerun on resume.
        setup = node(self.setup, rerun_on_resume=True)
        next_turns = node(self.next_turns)
        play_turn = node(self.play_turn, parallel_worker=True, rerun_on_resume=True)
        apply_turns = node(self.apply_turns)
        finish = node(self.finish)

        return Workflow(
            name=name,
            description="Plays a game of Imposter between LLM players, one per session.",
            edges=[
                Edge(from_node=START, to_node=setup),
                Edge(from_node=setup, to_node=next_turns),
                Edge(from_node=next_turns, to_node=play_turn, route=TURN_ROUTE),
                Edge(from_node=next_turns, to_node=finish, route=OVER_ROUTE),
                Edge(from_node=play_turn, to_node=apply_turns),
                Edge(from_node=apply_turns, to_node=next_turns),
            ],
        )

    async def setup(self, ctx: Context) -> AsyncGenerator[Event]:
        """Choose the secret word and create the game of the session.

        The session id is the game id. A session that already has a game keeps it, so
        running a finished session again plays nothing.

        Args:
            ctx: The workflow context of this node run.

        Yields:
            The ADK event of each engine event of the new game.

        Raises:
            ValueError: When there is no request in state and no default either.
        """
        if GAME_STATE_KEY in ctx.state:
            yield text_event(f"Session {ctx.session.id} already has a game.")
            return

        request_data = ctx.state.get(REQUEST_STATE_KEY)

        if request_data is not None:
            request = GameRequest.model_validate(request_data)
        elif self.default_request is not None:
            request = self.default_request
        else:
            message = f"The session {ctx.session.id} has no game request in its state."
            raise ValueError(message)

        secret = await self.words.resolve(
            options=request.words, with_hint=request.config.imposter_hint
        )
        game = Game.create(config=request.config, secret=secret, game_id=ctx.session.id)

        for event in save_game(ctx=ctx, game=game, published=0):
            yield event

    def next_turns(self, ctx: Context) -> Generator[Event]:
        """Start the next turn, or all turns of a parallel phase.

        Args:
            ctx: The workflow context of this node run.

        Yields:
            The ADK event of each `turn_started` event, then the seats whose turn
            started as output, routed to `play_turn`. Only the route to `finish` when
            the game is over.
        """
        game = load_game(ctx)

        if game.is_over:
            yield Event(actions=EventActions(route=OVER_ROUTE))
            return

        published = len(game.events)
        seats = game.pending_seats[:1] if game.is_sequential else game.pending_seats

        for seat in seats:
            game.start_turn(seat)

        yield from save_game(ctx=ctx, game=game, published=published)
        yield Event(output=seats, actions=EventActions(route=TURN_ROUTE))

    async def play_turn(self, ctx: Context, node_input: int) -> TurnResult:
        """Ask the player of a seat for its action, with one retry when it is invalid.

        The node is a parallel worker: ADK runs it once per started seat, at the same
        time. It only reads the game. Its `invoke_node` span is the turn level of the
        trace, with the spans of the player's agent and the judge below it.

        Args:
            ctx: The workflow context of this node run.
            node_input: The seat whose turn it is.

        Returns:
            The answer of the player, with its usage and errors.
        """
        seat = node_input
        game = load_game(ctx)
        span = mark_turn(game=game, seat=seat)
        player = self.players.player_for(game=game, seat=seat)
        view = game.view_for(seat)
        response: PhaseResponse | None = None
        rejection: ActionRejection | None = None
        usages: list[TurnUsage] = []
        errors: list[str] = []
        attempts = 0

        for _ in range(MAX_ATTEMPTS):
            attempts += 1

            try:
                response = await player.take_turn(
                    ctx=ctx,
                    view=view,
                    record_usage=usages.append,
                    retry_reason=rejection.reason if rejection else None,
                )
            except Exception as failure:
                # A failed child node raises an error that wraps the node's own error.
                error = getattr(failure, "error", failure)
                span.record_exception(error)
                errors.append(f"player failed: {error}")
                break

            rejection = await self.rejection(game=game, seat=seat, response=response)

            if rejection is None or not rejection.retryable:
                break

        guess_verdict = None

        if (
            isinstance(response, GuessResponse)
            and rejection is None
            and self.judge is not None
            and response.guess.strip()
            and not game.guess_is_exact(response.guess)
        ):
            guess_verdict = await self.judge.is_same_word(
                guess=response.guess, word=game.secret.word
            )

        result = TurnResult(
            seat=seat,
            response=response,
            rejection=rejection,
            guess_verdict=guess_verdict,
            usages=usages,
            errors=errors,
            attempts=attempts,
        )
        record_turn(
            span=span,
            attempts=attempts,
            response=response,
            problems=problems(result),
            truncated=game.is_truncated(response),
        )

        return result

    async def rejection(
        self, *, game: Game, seat: int, response: PhaseResponse
    ) -> ActionRejection | None:
        """Check a response against the rules of the phase and the clue judge.

        Args:
            game: The game.
            seat: The seat that gave the response.
            response: The structured output of the seat.

        Returns:
            Why the response is invalid, or `None` when it is valid.
        """
        rejection = game.rejection(seat=seat, response=response)

        # A clue that says the word is accepted: submitting it ends the game.
        if (
            rejection is not None
            or game.phase is not GamePhase.CLUE
            or not isinstance(response, ClueResponse)
            or game.clue_says_word(response.clue)
        ):
            return rejection

        # The judge runs the code checks itself before it asks the model.
        if self.judge is not None and game.config.model_clue_check:
            verdict = await self.judge.is_valid_clue(
                clue=response.clue, word=game.secret.word
            )
        else:
            verdict = clue_check(clue=response.clue, word=game.secret.word)

        if verdict is None or verdict.verdict:
            return None

        # Telling an imposter why would hint at the word, so it just passes.
        return ActionRejection(
            reason="the clue is too close to the secret word",
            retryable=game.seats[seat].role is not PlayerRole.IMPOSTER,
        )

    def apply_turns(self, ctx: Context, node_input: list[TurnResult]) -> Generator[Event]:
        """Apply the answers of a step to the game, in seat order.

        Usage is recorded first, because the tokens were spent even when the game is
        aborted for going over the budget. A rejected or missing response becomes the
        fallback action of the phase.

        Args:
            ctx: The workflow context of this node run.
            node_input: The answers of the turns of the step, in seat order.

        Yields:
            The ADK event of each new engine event.
        """
        game = load_game(ctx)
        published = len(game.events)

        for result in node_input:
            for usage in result.usages:
                game.record_usage(seat=result.seat, **usage.model_dump())

            if game.is_over:
                continue

            for problem in problems(result):
                game.record_player_error(seat=result.seat, message=problem)

            game.submit(
                seat=result.seat,
                response=result.response,
                rejection=result.rejection,
                judge_verdict=(
                    result.guess_verdict.verdict if result.guess_verdict else None
                ),
            )

        yield from save_game(ctx=ctx, game=game, published=published)

    def finish(self, ctx: Context) -> Event:
        """End the workflow with a line on how the game ended, which `adk web` shows.

        Args:
            ctx: The workflow context of this node run.

        Returns:
            The event with the line.
        """
        game = load_game(ctx)
        ending = game.outcome.value if game.outcome else game.phase.value

        return text_event(f"Game {game.game_id} is over: {ending}.")


def load_game(ctx: Context) -> Game:
    """Load the game of a session from its state.

    Args:
        ctx: The workflow context of a node run.

    Returns:
        The game, rebuilt from its snapshot. Changes to it are local until it is saved.
    """
    return Game.load(GameSnapshot.model_validate(ctx.state[GAME_STATE_KEY]))


def save_game(*, ctx: Context, game: Game, published: int) -> list[Event]:
    """Save a game to the state of its session and build the events of what is new.

    Args:
        ctx: The workflow context of a node run.
        game: The game.
        published: The number of engine events that already have an ADK event.

    Returns:
        The ADK event of each engine event after the published ones, for the node to
        yield. ADK attaches the state change to the first event the node yields.
    """
    ctx.state[GAME_STATE_KEY] = game.snapshot().model_dump(mode="json")

    return [game_event(event) for event in game.events[published:]]


def problems(result: TurnResult) -> list[str]:
    """List what went wrong in a turn: the errors and the rejection of the last answer.

    Args:
        result: The answer of a player.

    Returns:
        The messages, empty for an accepted answer without errors.
    """
    if result.rejection is None:
        return result.errors

    return [*result.errors, f"invalid action, falling back: {result.rejection.reason}"]


def game_event(event: BaseGameEvent) -> Event:
    """Build the ADK event of an engine event.

    Clients read the engine event from the custom metadata, under
    `GAME_EVENT_METADATA_KEY`. The content holds the same event as text, which is what
    `adk web` shows.

    Args:
        event: The engine event.

    Returns:
        The ADK event.
    """
    return Event(
        content=types.Content(
            role="model", parts=[types.Part(text=event.model_dump_json())]
        ),
        custom_metadata={GAME_EVENT_METADATA_KEY: event.model_dump(mode="json")},
    )


def text_event(text: str) -> Event:
    """Build a content event with a text message, as `adk web` shows it.

    Args:
        text: The message.

    Returns:
        The event.
    """
    return Event(content=types.Content(role="model", parts=[types.Part(text=text)]))
