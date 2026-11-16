"""Fixtures and helpers shared by the tests of several packages."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

import pytest
from fakes import FakeSeating, PlayersFactory, random_players
from google.adk.agents.context import Context
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.apps import App
from google.adk.events import Event
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.plugins import BasePlugin
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import START, Edge, Workflow, node
from google.genai import types
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import Field

from imposter.engine.game import GAME_STATE_KEY, Game, GameSnapshot
from imposter.judge.judge import Judge
from imposter.models.catalog import ModelCatalog, ModelCatalogEntry
from imposter.orchestration.setup import GameRequest
from imposter.orchestration.workflow import REQUEST_STATE_KEY, GameWorkflowBuilder
from imposter.words.options import SecretWordResolver
from imposter.words.picker import WordPicker

START_MESSAGE = types.Content(role="user", parts=[types.Part(text="Play.")])
"""The user message that starts a run in tests."""


def fake_builder(
    *,
    players_for: PlayersFactory = random_players,
    judge: Judge | None = None,
    default_request: GameRequest | None = None,
) -> GameWorkflowBuilder:
    """Build a workflow builder with random words and fake players, without models."""
    return GameWorkflowBuilder(
        words=SecretWordResolver(picker=WordPicker.load(seed=3), generator=None),
        players=FakeSeating(players_for),
        judge=judge,
        default_request=default_request,
    )


async def run_events(
    workflow: Workflow,
    *,
    state: dict[str, Any] | None = None,
    streaming: bool = False,
    plugins: list[BasePlugin] | None = None,
    session_id: str = "game-1",
) -> tuple[list[Event], dict[str, Any]]:
    """Run a workflow once in a new session and collect its events and final state."""
    app = App(name="test", root_agent=workflow, plugins=plugins or [])
    runner = Runner(app=app, session_service=InMemorySessionService())
    sessions = runner.session_service
    await sessions.create_session(
        app_name="test", user_id="u", session_id=session_id, state=state
    )
    mode = StreamingMode.SSE if streaming else StreamingMode.NONE
    events = [
        event
        async for event in runner.run_async(
            user_id="u",
            session_id=session_id,
            new_message=START_MESSAGE,
            run_config=RunConfig(streaming_mode=mode),
        )
    ]
    session = await sessions.get_session(
        app_name="test", user_id="u", session_id=session_id
    )
    assert session is not None

    return events, dict(session.state)


async def play_workflow(
    builder: GameWorkflowBuilder,
    *,
    request: GameRequest | None = None,
    game: Game | None = None,
    plugins: list[BasePlugin] | None = None,
) -> Game:
    """Play a game through the workflow, from a request or from a game already set up."""
    state: dict[str, Any] = {}

    if request is not None:
        state[REQUEST_STATE_KEY] = request.model_dump(mode="json")

    if game is not None:
        state[GAME_STATE_KEY] = game.snapshot().model_dump(mode="json")

    _, final_state = await run_events(builder.build(), state=state, plugins=plugins)

    return Game.load(GameSnapshot.model_validate(final_state[GAME_STATE_KEY]))


async def run_in_node[ResultT](
    body: Callable[[Context], Awaitable[ResultT]], *, streaming: bool = False
) -> tuple[ResultT, list[Event]]:
    """Run a coroutine function in a workflow node and return its result and the events.

    The result is kept as the object it is, because ADK turns node outputs into JSON.
    """
    results: list[ResultT] = []

    async def body_node(ctx: Context) -> None:
        results.append(await body(ctx))

    workflow = Workflow(
        name="test_workflow",
        edges=[Edge(from_node=START, to_node=node(body_node, rerun_on_resume=True))],
    )
    events, _ = await run_events(workflow, streaming=streaming)

    return results[0], events


class ReplayLlm(BaseLlm):
    """An ADK model that replays canned text replies and records every request.

    Attributes:
        replies: The remaining replies, as answer text or an error to raise.
        requests: The requests the model received, in order.
    """

    model: str = "fake"
    replies: list[str | Exception] = Field(default_factory=list)
    requests: list[LlmRequest] = Field(default_factory=list)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse]:
        self.requests.append(llm_request.model_copy(deep=True))
        reply = self.replies.pop(0)

        if isinstance(reply, Exception):
            raise reply

        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=reply)])
        )

    def prompt(self, index: int = -1) -> str:
        """Join the text of the user message of a recorded request."""
        content = self.requests[index].contents[-1]

        return "".join(part.text or "" for part in content.parts or [])


@pytest.fixture(scope="function")
def replay_llm() -> ReplayLlm:
    """A replaying model without replies, to be filled by the test."""
    return ReplayLlm()


@pytest.fixture(scope="session")
def flash_lite() -> ModelCatalogEntry:
    """The catalog entry of Gemini Flash-Lite, the judge and generator model."""
    return ModelCatalog.load().entry("gemini-flash-lite")


@pytest.fixture(scope="session")
def span_exporter() -> InMemorySpanExporter:
    """Collect spans in memory, through the global tracer provider, which is set once."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    return exporter
