"""Fixtures shared by the tests of several packages."""

from collections.abc import AsyncGenerator, Callable, Sequence
from typing import Any

import pytest
from google.adk.agents.context import Context
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.apps import App
from google.adk.events import Event
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import START, Edge, Node, Workflow
from google.genai import types
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import Field, SkipValidation

from imposter.engine.game import Game
from imposter.engine.views import PlayerView
from imposter.judge.base import JudgeProtocol
from imposter.models.catalog import ModelCatalog, ModelCatalogEntry
from imposter.orchestration.runner import GameRunner
from imposter.orchestration.setup import GameSetup
from imposter.players.base import PlayerProtocol, PlayerResponse, TurnUsage
from imposter.players.fake import RandomPlayer
from imposter.words.options import SecretWordResolver
from imposter.words.picker import WordPicker

type PlayersFactory = Callable[[Game], Sequence[PlayerProtocol]]
"""Builds the players of a game, one per seat in seat order."""


def random_players(game: Game) -> list[RandomPlayer]:
    """Seat a random player that reports 100 tokens per turn for every seat."""
    return [
        RandomPlayer(
            seed=seat.seat,
            usage=TurnUsage(
                model_id=seat.player.model_id, input_tokens=90, output_tokens=10
            ),
        )
        for seat in game.seats
    ]


class FakeGameSetup(GameSetup):
    """A game setup with random words from the built-in categories and fake players.

    Attributes:
        players_for: Builds the players of a game.
    """

    def __init__(
        self,
        *,
        players_for: PlayersFactory = random_players,
        judge: JudgeProtocol | None = None,
    ) -> None:
        resolver = SecretWordResolver(picker=WordPicker.load(seed=3), generator=None)
        super().__init__(catalog=ModelCatalog.load(), resolver=resolver, judge=judge)
        self.players_for = players_for

    def runner_for(self, game: Game) -> GameRunner:
        return GameRunner(players=self.players_for(game), judge=self.judge)


class TurnsNode(Node):
    """A workflow node that has a player take turns, the way a turn node does.

    Attributes:
        player: The player.
        turns: The view and retry reason of each turn, in order.
        rerun_on_resume: Set, because ADK requires it of nodes that run child nodes.
    """

    player: SkipValidation[PlayerProtocol]
    turns: list[tuple[PlayerView, str | None]]
    rerun_on_resume: bool = True

    async def run_node_impl(
        self, *, ctx: Context, node_input: Any
    ) -> AsyncGenerator[Event]:
        responses = [
            await self.player.take_turn(view=view, retry_reason=reason, ctx=ctx)
            for view, reason in self.turns
        ]

        yield Event(output=responses)


async def run_turns(
    player: PlayerProtocol,
    turns: list[tuple[PlayerView, str | None]],
    *,
    streaming: bool = False,
) -> tuple[list[PlayerResponse], list[Event]]:
    """Have a player take turns in one workflow run and collect every event of the run."""
    sessions = InMemorySessionService()
    node = TurnsNode(name="turn", player=player, turns=turns)
    workflow = Workflow(name="turns", edges=[Edge(from_node=START, to_node=node)])
    runner = Runner(app=App(name="test", root_agent=workflow), session_service=sessions)
    session = await sessions.create_session(app_name="test", user_id="u")
    message = types.Content(role="user", parts=[types.Part(text="Play.")])
    mode = StreamingMode.SSE if streaming else StreamingMode.NONE
    events = [
        event
        async for event in runner.run_async(
            user_id="u",
            session_id=session.id,
            new_message=message,
            run_config=RunConfig(streaming_mode=mode),
        )
    ]
    [responses] = [
        event.output for event in events if event.author == "turns" and event.output
    ]

    return responses, events


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
