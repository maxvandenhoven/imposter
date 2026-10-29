from collections.abc import AsyncGenerator
from typing import Any

import litellm
import pytest
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import errors, types
from pydantic import Field

from imposter.config import GameConfig, GamePhase, PlayerConfig, PlayerRole, SecretWord
from imposter.engine.game import Game
from imposter.engine.views import PlayerView
from imposter.models.catalog import ModelCatalogEntry, ModelPrice, ModelProvider, ModelVia
from imposter.players.adk_player import AdkPlayer
from imposter.players.base import (
    PHASE_RESPONSE_TYPES,
    ClueResponse,
    DiscussionResponse,
    PlayerResponse,
    TurnUsage,
    VoteResponse,
)

WORD = "giraffe"


def gemini_error(code: int, status: str) -> errors.APIError:
    """Build the error `google-genai` raises for an HTTP status."""
    error_type = errors.ClientError if code < 500 else errors.ServerError

    return error_type(code, {"error": {"code": code, "status": status, "message": "x"}})


def litellm_rate_limit() -> litellm.RateLimitError:
    """Build the error LiteLLM raises for a rate limit."""
    return litellm.RateLimitError(
        message="slow down", llm_provider="vertex_ai", model="m"
    )


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
        self.requests.append(llm_request)
        reply = self.replies.pop(0)

        if isinstance(reply, Exception):
            raise reply

        if isinstance(reply, LlmResponse):
            yield reply
            return

        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text="hmm", thought=True), types.Part(text=reply)],
            ),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=100, candidates_token_count=10, thoughts_token_count=5
            ),
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


def new_player(
    *,
    game: Game,
    replies: list[Any],
    structured: bool = True,
    role: PlayerRole | None = None,
    max_retries: int = 2,
) -> tuple[AdkPlayer, FakeLlm, PlayerView]:
    """Build a player for the current seat, or the first seat of a role, and its view."""
    seat = game.pending_seats[0]

    if role is not None:
        seat = next(s.seat for s in game.seats if s.role is role)

    model = FakeLlm(replies=replies)
    player = AdkPlayer(
        entry=entry(structured=structured),
        seat=seat,
        model=model,
        timeout_seconds=1,
        max_retries=max_retries,
        backoff_seconds=0,
    )

    return player, model, game.view_for(seat)


def request_text(request: LlmRequest) -> str:
    """Join the text of every message in a request."""
    return "\n".join(
        part.text or "" for content in request.contents for part in content.parts or []
    )


async def test_structured_output_turn_returns_parsed_output_and_usage() -> None:
    game = new_game()
    player, model, view = new_player(
        game=game, replies=['{"clue": "neck", "private_reasoning": "long"}']
    )

    response = await player.take_turn(view)

    assert response == PlayerResponse(
        output=ClueResponse(clue="neck", private_reasoning="long"),
        usage=TurnUsage(
            model_id="fake-model", input_tokens=100, output_tokens=10, thinking_tokens=5
        ),
    )
    request = model.requests[0]
    assert request.config.response_schema is ClueResponse
    assert "social deduction word game" in str(request.config.system_instruction)
    assert "# Game rules" not in str(request.config.system_instruction)
    assert "# Game rules" in request_text(request)
    assert "It is clue round 1" in request_text(request)
    assert "JSON schema" not in request_text(request)


async def test_instruction_is_rendered_from_the_view_of_the_seat() -> None:
    game = new_game()
    reply = '{"clue": "neck"}'
    civilian, civilian_model, civilian_view = new_player(
        game=game, replies=[reply], role=PlayerRole.CIVILIAN
    )
    imposter, imposter_model, imposter_view = new_player(
        game=game, replies=[reply], role=PlayerRole.IMPOSTER
    )

    await civilian.take_turn(civilian_view)
    await imposter.take_turn(imposter_view)

    civilian_prompt = request_text(civilian_model.requests[0])
    imposter_prompt = request_text(imposter_model.requests[0])
    assert f'The secret word is "{WORD}"' in civilian_prompt
    assert WORD not in imposter_prompt
    assert "You do not know the secret word." in imposter_prompt


async def test_turns_send_no_conversation_history() -> None:
    game = new_game()
    player, model, view = new_player(
        game=game, replies=['{"clue": "neck"}', '{"clue": "spots"}']
    )

    await player.take_turn(view)
    await player.take_turn(view, retry_reason="the clue was already given")

    first, second = model.requests
    assert len(second.contents) == len(first.contents)
    assert "neck" not in request_text(second)
    assert "rejected: the clue was already given" in request_text(second)


async def test_json_in_prompt_turn_parses_fenced_json() -> None:
    game = new_game()
    reply = 'Here you go:\n```json\n{"clue": "neck", "private_reasoning": "tall"}\n```'
    player, model, view = new_player(game=game, replies=[reply], structured=False)

    response = await player.take_turn(view)

    assert response.output == ClueResponse(clue="neck", private_reasoning="tall")
    request = model.requests[0]
    assert request.config.response_schema is None
    assert "Answer with only a JSON object" in request_text(request)


async def test_invalid_answer_is_retried_once_with_the_error() -> None:
    game = new_game()
    player, model, view = new_player(
        game=game, replies=["neck", '{"clue": "neck"}'], structured=False
    )

    response = await player.take_turn(view)

    assert response.output == ClueResponse(clue="neck")
    assert response.error is None
    assert response.usage is not None and response.usage.input_tokens == 200
    assert "not a valid JSON object" in request_text(model.requests[1])


async def test_second_invalid_answer_gives_up_with_an_error() -> None:
    game = new_game()
    player, _, view = new_player(
        game=game, replies=['{"hint": "neck"}', "still no json"], structured=False
    )

    response = await player.take_turn(view)

    assert response.output is None
    assert response.error is not None
    assert response.error.startswith("invalid answer, falling back:")
    assert response.usage is not None and response.usage.output_tokens == 20


async def test_transient_errors_are_retried() -> None:
    game = new_game()
    player, model, view = new_player(
        game=game,
        replies=[
            gemini_error(429, "RESOURCE_EXHAUSTED"),
            litellm_rate_limit(),
            gemini_error(503, "UNAVAILABLE"),
            '{"clue": "neck"}',
        ],
        max_retries=3,
    )

    response = await player.take_turn(view)

    assert response.output == ClueResponse(clue="neck")
    assert len(model.requests) == 4


async def test_persistent_errors_give_up_with_an_error() -> None:
    game = new_game()
    player, model, view = new_player(game=game, replies=[litellm_rate_limit()] * 3)

    response = await player.take_turn(view)

    assert response.output is None
    assert response.usage is None
    assert response.error is not None
    assert "error RateLimitError" in response.error
    assert len(model.requests) == 3


async def test_other_errors_are_not_retried() -> None:
    game = new_game()
    player, model, view = new_player(
        game=game, replies=[gemini_error(400, "INVALID_ARGUMENT")]
    )

    response = await player.take_turn(view)

    assert response.output is None
    assert len(model.requests) == 1


async def test_error_responses_give_up_with_an_error() -> None:
    game = new_game()
    blocked = LlmResponse(error_code="SAFETY", error_message="Blocked")
    player, _, view = new_player(game=game, replies=[blocked])

    response = await player.take_turn(view)

    assert response.output is None
    assert response.error is not None
    assert "error SAFETY: Blocked" in response.error


async def test_each_phase_uses_its_response_type() -> None:
    game = new_game()
    player, _, _ = new_player(game=game, replies=[])

    assert player.agents.keys() == PHASE_RESPONSE_TYPES.keys()
    assert player.agents[GamePhase.VOTE].output_schema is VoteResponse
    assert player.agents[GamePhase.DISCUSSION].output_schema is DiscussionResponse
    assert player.agents[GamePhase.CLUE].include_contents == "none"


async def test_view_of_another_seat_is_rejected() -> None:
    game = new_game()
    player, _, view = new_player(game=game, replies=[])
    other = game.view_for((view.seat + 1) % 3)

    with pytest.raises(ValueError, match="cannot act on the view of seat"):
        await player.take_turn(other)
