import os

import litellm
from google.adk.models import BaseLlm, Gemini
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from imposter.config import GamePhase
from imposter.models.catalog import ModelCatalogEntry, ModelThinking, ModelVia

MODEL_CALL_TIMEOUT_SECONDS = 60
"""The time limit of one model call (README D28)."""

MODEL_CALL_RETRIES = 2
"""The retries of a model call on a timeout, rate limit or server error (README D28)."""

RETRY_STATUS_CODES = [408, 429, 500, 502, 503, 504]
"""The HTTP status codes on which a Gemini call is retried."""

PHASE_MAX_OUTPUT_TOKENS: dict[GamePhase, int] = {
    GamePhase.CLUE: 400,
    GamePhase.DISCUSSION: 800,
    GamePhase.VOTE: 400,
    GamePhase.GUESS: 400,
    GamePhase.DEBRIEF: 800,
}
"""The answer tokens per phase, a cost guardrail (README D29): room for the JSON with a
clue or vote and the private reasoning, more for statements and reflections."""

THINKING_TOKENS: dict[ModelThinking, int] = {
    ModelThinking.OFF: 1024,
    ModelThinking.LOW: 2048,
    ModelThinking.HIGH: 8192,
}
"""The extra output tokens for native thinking, which counts towards the output limit.
Models that cannot switch thinking off still think a little, hence the room for `off`."""

THINKING_LEVELS: dict[ModelThinking, types.ThinkingLevel] = {
    ModelThinking.OFF: types.ThinkingLevel.MINIMAL,
    ModelThinking.LOW: types.ThinkingLevel.LOW,
    ModelThinking.HIGH: types.ThinkingLevel.HIGH,
}
"""The Gemini thinking level of each catalog setting. LiteLLM maps it for other models."""


def adk_model(entry: ModelCatalogEntry) -> BaseLlm:
    """Build the ADK model object of a catalog entry, always on Vertex AI (README D5).

    The client of the model owns the timeout and the retries with exponential backoff
    on rate limits and server errors. The project comes from `GOOGLE_CLOUD_PROJECT` and
    the credentials from ADC.

    Args:
        entry: The catalog entry.

    Returns:
        A native `Gemini` model or a `LiteLlm` model for the entry's location.
    """
    if entry.via is ModelVia.NATIVE:
        return Gemini(
            model=entry.adk_model,
            client_kwargs={
                "vertexai": True,
                "location": entry.location,
                "http_options": types.HttpOptions(
                    timeout=MODEL_CALL_TIMEOUT_SECONDS * 1000
                ),
            },
            retry_options=types.HttpRetryOptions(
                attempts=MODEL_CALL_RETRIES + 1, http_status_codes=RETRY_STATUS_CODES
            ),
        )

    # LiteLLM prints a provider list for models it has no price for, such as new ones.
    litellm.suppress_debug_info = True
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    vertex_args = {"vertex_project": project} if project else {}

    return LiteLlm(
        model=entry.adk_model,
        vertex_location=entry.location,
        timeout=MODEL_CALL_TIMEOUT_SECONDS,
        num_retries=MODEL_CALL_RETRIES,
        **vertex_args,
    )


def generate_content_config(
    *, entry: ModelCatalogEntry, phase: GamePhase, temperature: float | None = None
) -> types.GenerateContentConfig:
    """Build the generation settings of a catalog entry for one phase.

    Args:
        entry: The catalog entry.
        phase: The phase the settings are for, which sets the output token limit.
        temperature: A temperature that overrides the entry's default, if given.

    Returns:
        The temperature, output token limit and thinking setting.
    """
    thinking_config = None

    if entry.via is ModelVia.NATIVE or entry.thinking is not ModelThinking.OFF:
        thinking_config = types.ThinkingConfig(
            thinking_level=THINKING_LEVELS[entry.thinking]
        )

    return types.GenerateContentConfig(
        temperature=entry.temperature if temperature is None else temperature,
        max_output_tokens=PHASE_MAX_OUTPUT_TOKENS[phase]
        + THINKING_TOKENS[entry.thinking],
        thinking_config=thinking_config,
    )
