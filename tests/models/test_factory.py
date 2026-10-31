import pytest
from google.adk.models import Gemini
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from imposter.config import GamePhase
from imposter.models.catalog import (
    ModelCatalogEntry,
    ModelPrice,
    ModelProvider,
    ModelThinking,
    ModelVia,
)
from imposter.models.factory import (
    LITELLM_CALL_TIMEOUT_SECONDS,
    MODEL_CALL_RETRIES,
    MODEL_CALL_TIMEOUT_SECONDS,
    PHASE_MAX_OUTPUT_TOKENS,
    REASONING_EFFORTS,
    RETRY_STATUS_CODES,
    THINKING_TOKENS,
    adk_model,
    generate_content_config,
)


def entry(
    *,
    via: ModelVia,
    thinking: ModelThinking = ModelThinking.OFF,
    always_reasons: bool = False,
) -> ModelCatalogEntry:
    """Build a catalog entry for a native or LiteLLM model."""
    return ModelCatalogEntry(
        id="m",
        display_name="M",
        provider=ModelProvider.GOOGLE
        if via is ModelVia.NATIVE
        else ModelProvider.ANTHROPIC,
        adk_model="gemini-x" if via is ModelVia.NATIVE else "vertex_ai/claude-x",
        via=via,
        location="us-central1",
        thinking=thinking,
        always_reasons=always_reasons,
        temperature=0.7,
        price_per_mtok=ModelPrice(input=1, output=2),
    )


def test_adk_model_builds_gemini_on_vertex_in_the_entry_location() -> None:
    model = adk_model(entry(via=ModelVia.NATIVE))

    assert isinstance(model, Gemini)
    assert model.model == "gemini-x"
    assert model.client_kwargs is not None
    assert model.client_kwargs["vertexai"] is True
    assert model.client_kwargs["location"] == "us-central1"
    assert (
        model.client_kwargs["http_options"].timeout == MODEL_CALL_TIMEOUT_SECONDS * 1000
    )
    assert model.retry_options is not None
    assert model.retry_options.attempts == MODEL_CALL_RETRIES + 1
    assert model.retry_options.http_status_codes == RETRY_STATUS_CODES


def test_adk_model_builds_litellm_with_project_and_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "sandbox")

    model = adk_model(entry(via=ModelVia.LITELLM))

    assert isinstance(model, LiteLlm)
    assert model.model == "vertex_ai/claude-x"
    assert model._additional_args["vertex_project"] == "sandbox"
    assert model._additional_args["vertex_location"] == "us-central1"
    assert model._additional_args["timeout"] == LITELLM_CALL_TIMEOUT_SECONDS
    assert model._additional_args["num_retries"] == MODEL_CALL_RETRIES


@pytest.mark.parametrize(
    ("thinking", "effort"),
    [
        (ModelThinking.OFF, "low"),
        (ModelThinking.LOW, "low"),
        (ModelThinking.HIGH, "high"),
    ],
)
def test_adk_model_maps_thinking_to_reasoning_effort_for_reasoning_models(
    thinking: ModelThinking, effort: str
) -> None:
    model = adk_model(entry(via=ModelVia.LITELLM, thinking=thinking, always_reasons=True))

    assert isinstance(model, LiteLlm)
    assert model._additional_args["reasoning_effort"] == effort
    assert REASONING_EFFORTS[thinking] == effort


def test_adk_model_sends_no_reasoning_effort_to_models_that_do_not_always_reason() -> (
    None
):
    model = adk_model(entry(via=ModelVia.LITELLM))

    assert isinstance(model, LiteLlm)
    assert "reasoning_effort" not in model._additional_args


@pytest.mark.parametrize("phase", list(PHASE_MAX_OUTPUT_TOKENS))
def test_generate_content_config_limits_output_per_phase(phase: GamePhase) -> None:
    config = generate_content_config(entry=entry(via=ModelVia.NATIVE), phase=phase)

    assert config.max_output_tokens == (
        PHASE_MAX_OUTPUT_TOKENS[phase] + THINKING_TOKENS[ModelThinking.OFF]
    )
    assert config.temperature == 0.7


def test_generate_content_config_overrides_the_temperature() -> None:
    config = generate_content_config(
        entry=entry(via=ModelVia.NATIVE), phase=GamePhase.CLUE, temperature=0.0
    )

    assert config.temperature == 0.0


@pytest.mark.parametrize(
    ("via", "thinking", "level"),
    [
        (ModelVia.NATIVE, ModelThinking.OFF, types.ThinkingLevel.MINIMAL),
        (ModelVia.NATIVE, ModelThinking.HIGH, types.ThinkingLevel.HIGH),
        (ModelVia.LITELLM, ModelThinking.OFF, None),
        (ModelVia.LITELLM, ModelThinking.LOW, types.ThinkingLevel.LOW),
    ],
)
def test_generate_content_config_sets_the_thinking_level(
    via: ModelVia, thinking: ModelThinking, level: types.ThinkingLevel | None
) -> None:
    config = generate_content_config(
        entry=entry(via=via, thinking=thinking), phase=GamePhase.VOTE
    )
    configured = config.thinking_config.thinking_level if config.thinking_config else None

    assert configured == level
