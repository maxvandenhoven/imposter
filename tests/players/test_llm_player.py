from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from conftest import run_in_node
from google.adk.agents.context import Context
from google.adk.events import Event
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import errors, types
from litellm.exceptions import MidStreamFallbackError
from pydantic import Field

from imposter.config import GameConfig, PlayerConfig, PlayerRole, SecretWord
from imposter.engine.game import Game
from imposter.engine.responses import ClueResponse, PhaseResponse
from imposter.engine.views import PlayerView
from imposter.models.catalog import (
    ModelCatalog,
    ModelCatalogEntry,
    ModelPrice,
    ModelProvider,
    ModelVia,
)
from imposter.players.base import TurnUsage
from imposter.players.llm_player import ANSWER_RETRY, LlmPlayer, LlmPlayerSeating

WORD = "giraffe"

FAST_RETRY = ANSWER_RETRY.model_copy(update={"initial_delay": 0.0, "jitter": 0.0})
"""The retries of a turn without the waits between them."""


class FakeLlm(BaseLlm):
    """An ADK model that replays canned replies and records every request.

    Attributes:
        replies: The remaining replies: answer text, an `LlmResponse` or an error.
        requests: The requests the model received, in order.
    """

    model: str = "fake"
    replies: list[Any] = Field(default_factory=list)
    requests: list[LlmRequest] = Field(default_factory=list)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse]:
        self.requests.append(llm_request.model_copy(deep=True))
        reply = self.replies.pop(0)

        if isinstance(reply, Exception):
            raise reply

        if isinstance(reply, LlmResponse):
            yield reply
            return

        usage = types.GenerateContentResponseUsageMetadata(
            prompt_token_count=100, candidates_token_count=10, thoughts_token_count=5
        )

        # Like Gemini, the last chunk carries the usage, and so does the full response.
        if stream:
            half = len(reply) // 2

            for chunk, chunk_usage in ((reply[:half], None), (reply[half:], usage)):
                yield LlmResponse(
                    content=types.Content(role="model", parts=[types.Part(text=chunk)]),
                    usage_metadata=chunk_usage,
                    partial=True,
                )

        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text="hmm", thought=True), types.Part(text=reply)],
            ),
            usage_metadata=usage,
        )


def entry(*, structured: bool) -> ModelCatalogEntry:
    """Build a catalog entry with or without native structured output."""
    return ModelCatalogEntry(
        id="fake-model",
        display_name="Fake",
        provider=ModelProvider.GOOGLE,
        adk_model="fake",
        via=ModelVia.NATIVE,
        supports_structured_output=structured,
        price_per_mtok=ModelPrice(input=1, output=2),
    )


def new_game() -> Game:
    """Create a seeded three player game in its first clue turn."""
    config = GameConfig(players=[PlayerConfig(model_id="fake-model")] * 3, seed=2)
    game = Game.create(config=config, secret=SecretWord(word=WORD, category="animals"))
    game.start_turn(game.pending_seats[0])

    return game


def request_text(request: LlmRequest) -> str:
    """Join the text of every message in a request."""
    return "\n".join(
        part.text or "" for content in request.contents for part in content.parts or []
    )


@dataclass
class Turn:
    """What one turn of a player gave.

    Attributes:
        response: The answer, `None` when the player failed.
        failure: The error of a player that failed, with the node error unwrapped.
        usages: The tokens of each model call of the turn.
        events: The ADK events of the run.
    """

    response: PhaseResponse | None = None
    failure: Exception | None = None
    usages: list[TurnUsage] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)


def new_player(
    *,
    game: Game,
    replies: list[Any],
    structured: bool = True,
    role: PlayerRole | None = None,
) -> tuple[LlmPlayer, FakeLlm, PlayerView]:
    """Build a player for the current seat, or the first seat of a role, and its view."""
    seat = game.pending_seats[0]

    if role is not None:
        seat = next(s.seat for s in game.seats if s.role is role)

    model = FakeLlm(replies=replies)
    player = LlmPlayer(
        entry=entry(structured=structured), model=model, retry_config=FAST_RETRY
    )

    return player, model, game.view_for(seat)


async def take_turn(
    player: LlmPlayer,
    view: PlayerView,
    *,
    retry_reason: str | None = None,
    streaming: bool = False,
) -> Turn:
    """Have a player take one turn in a workflow node, the way the turn node does."""
    turn = Turn()

    async def body(ctx: Context) -> None:
        try:
            turn.response = await player.take_turn(
                ctx=ctx,
                view=view,
                record_usage=turn.usages.append,
                retry_reason=retry_reason,
            )
        except Exception as failure:
            turn.failure = getattr(failure, "error", failure)

    _, turn.events = await run_in_node(body, streaming=streaming)

    return turn


async def test_structured_output_turn_returns_parsed_output_and_usage() -> None:
    game = new_game()
    player, model, view = new_player(
        game=game, replies=['{"clue": "neck", "private_reasoning": "long"}']
    )

    turn = await take_turn(player, view)

    assert turn.response == ClueResponse(clue="neck", private_reasoning="long")
    assert turn.usages == [
        TurnUsage(
            model_id="fake-model", input_tokens=100, output_tokens=10, thinking_tokens=5
        )
    ]
    request = model.requests[0]
    assert request.config.response_schema is ClueResponse
    assert "social deduction word game" in str(request.config.system_instruction)
    assert "# Game rules" not in str(request.config.system_instruction)
    assert "# Game rules" in request_text(request)
    assert "It is clue round 1" in request_text(request)
    assert "JSON schema" not in request_text(request)


async def test_streaming_turn_yields_partial_events_and_counts_usage_once() -> None:
    game = new_game()
    reply = '{"clue": "neck", "private_reasoning": "long"}'
    player, _, view = new_player(game=game, replies=[reply])

    turn = await take_turn(player, view, streaming=True)

    partials = [event for event in turn.events if event.partial]
    chunks = [
        part.text
        for event in partials
        if event.content and event.content.parts
        for part in event.content.parts
    ]
    assert turn.response == ClueResponse(clue="neck", private_reasoning="long")
    assert [usage.input_tokens for usage in turn.usages] == [100]
    assert {event.author for event in partials} == {f"player_{view.seat}_clue"}
    assert "".join(chunk or "" for chunk in chunks) == reply


async def test_turn_without_streaming_yields_no_partial_events() -> None:
    game = new_game()
    player, _, view = new_player(game=game, replies=['{"clue": "neck"}'])

    turn = await take_turn(player, view)

    assert not any(event.partial for event in turn.events)


async def test_instruction_is_rendered_from_the_view_of_the_seat() -> None:
    game = new_game()
    reply = '{"clue": "neck"}'
    civilian, civilian_model, civilian_view = new_player(
        game=game, replies=[reply], role=PlayerRole.CIVILIAN
    )
    imposter, imposter_model, imposter_view = new_player(
        game=game, replies=[reply], role=PlayerRole.IMPOSTER
    )

    await take_turn(civilian, civilian_view)
    await take_turn(imposter, imposter_view)

    civilian_prompt = request_text(civilian_model.requests[0])
    imposter_prompt = request_text(imposter_model.requests[0])
    assert f'The secret word is "{WORD}"' in civilian_prompt
    assert WORD not in imposter_prompt
    assert "You do not know the secret word." in imposter_prompt


async def test_braces_in_the_instruction_are_not_filled_from_session_state() -> None:
    game = new_game()
    player, model, view = new_player(game=game, replies=['{"clue": "neck"}'])
    braced = view.model_copy(update={"name": "{game}"})

    turn = await take_turn(player, braced)

    assert turn.failure is None
    assert "You are {game}" in request_text(model.requests[0])


async def test_turns_send_no_conversation_history() -> None:
    game = new_game()
    player, model, view = new_player(
        game=game, replies=['{"clue": "neck"}', '{"clue": "spots"}']
    )
    responses: list[PhaseResponse] = []

    async def two_attempts(ctx: Context) -> None:
        for reason in (None, "the clue was already given"):
            responses.append(
                await player.take_turn(
                    ctx=ctx, view=view, record_usage=print, retry_reason=reason
                )
            )

    await run_in_node(two_attempts)

    first, second = model.requests
    assert responses[1] == ClueResponse(clue="spots")
    assert len(second.contents) == len(first.contents)
    assert "neck" not in request_text(second)
    assert "rejected: the clue was already given" in request_text(second)


async def test_json_in_prompt_turn_sends_no_schema_and_parses_fenced_json() -> None:
    game = new_game()
    reply = """```json\n{"clue": "neck", "private_reasoning": "tall"}\n```"""
    player, model, view = new_player(game=game, replies=[reply], structured=False)

    turn = await take_turn(player, view)

    assert turn.response == ClueResponse(clue="neck", private_reasoning="tall")
    request = model.requests[0]
    assert request.config.response_schema is None
    assert request.config.response_mime_type is None
    assert "Answer with only a JSON object" in request_text(request)


async def test_answer_that_misses_the_schema_is_asked_again_by_adk() -> None:
    game = new_game()
    player, model, view = new_player(
        game=game, replies=['{"hint": "neck"}', '{"clue": "neck"}'], structured=False
    )

    turn = await take_turn(player, view)

    assert turn.response == ClueResponse(clue="neck")
    assert [usage.input_tokens for usage in turn.usages] == [100, 100]
    assert request_text(model.requests[1]) == request_text(model.requests[0])


async def test_last_answer_that_misses_the_schema_fails_the_turn() -> None:
    game = new_game()
    player, model, view = new_player(
        game=game,
        replies=['{"hint": "neck"}', "still no json", "nor this"],
        structured=False,
    )

    turn = await take_turn(player, view)

    assert turn.response is None
    assert type(turn.failure).__name__ == "ValidationError"
    assert len(model.requests) == FAST_RETRY.max_attempts
    assert sum(usage.output_tokens for usage in turn.usages) == 30


async def test_model_errors_fail_the_turn_without_asking_again() -> None:
    game = new_game()
    error = errors.ClientError(
        429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota"}}
    )
    player, model, view = new_player(game=game, replies=[error])

    turn = await take_turn(player, view)

    assert turn.response is None
    assert "RESOURCE_EXHAUSTED" in str(turn.failure)
    assert len(model.requests) == 1


async def test_broken_streams_are_asked_again_up_to_the_attempt_limit() -> None:
    game = new_game()
    broken = MidStreamFallbackError(
        message="Timeout on reading data.", model="m", llm_provider="vertex_ai"
    )
    player, model, view = new_player(game=game, replies=[broken, broken, broken])

    turn = await take_turn(player, view)

    assert turn.response is None
    assert isinstance(turn.failure, MidStreamFallbackError)
    assert len(model.requests) == FAST_RETRY.max_attempts


async def test_error_responses_fail_the_turn_with_the_error() -> None:
    game = new_game()
    blocked = LlmResponse(error_code="SAFETY", error_message="Blocked")
    player, model, view = new_player(game=game, replies=[blocked])

    turn = await take_turn(player, view)

    assert turn.response is None
    assert str(turn.failure) == "SAFETY: Blocked"
    assert len(model.requests) == 1


def test_agent_of_a_turn_is_a_plain_llm_agent_for_the_phase() -> None:
    game = new_game()
    player, _, view = new_player(game=game, replies=[])

    agent = player.agent(view=view, record_usage=print)

    assert agent.name == f"player_{view.seat}_clue"
    assert agent.output_schema is ClueResponse
    assert agent.include_contents == "none"
    assert agent.retry_config == FAST_RETRY
    assert agent.tools == []


def test_seating_gives_each_seat_the_model_of_its_config() -> None:
    catalog = ModelCatalog.load()
    config = GameConfig(
        players=catalog.player_configs(["gemini-flash", "gemini-flash", "gpt-oss"]),
        temperature=0.3,
        seed=1,
    )
    game = Game.create(config=config, secret=SecretWord(word=WORD))
    seating = LlmPlayerSeating(catalog)

    players = [seating.player_for(game=game, seat=seat.seat) for seat in game.seats]

    assert [player.entry.id for player in players] == [
        seat.player.model_id for seat in game.seats
    ]
    assert all(player.temperature == 0.3 for player in players)
    assert len({id(player.model) for player in players}) == 2
