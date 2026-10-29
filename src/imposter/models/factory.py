import os

import litellm
from google.adk.models import BaseLlm, Gemini
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from imposter.config import GamePhase
from imposter.models.catalog import ModelCatalogEntry, ModelThinking, ModelVia

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

    The project comes from `GOOGLE_CLOUD_PROJECT` and the credentials from ADC.

    Args:
        entry: The catalog entry.

    Returns:
        A native `Gemini` model or a `LiteLlm` model for the entry's location.
    """
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")

    if entry.via is ModelVia.NATIVE:
        return Gemini(
            model=entry.adk_model,
            client_kwargs={"vertexai": True, "location": entry.location},
        )

    # LiteLLM prints a provider list for models it has no price for, such as new ones.
    litellm.suppress_debug_info = True

    if project:
        return LiteLlm(
            model=entry.adk_model, vertex_project=project, vertex_location=entry.location
        )

    return LiteLlm(model=entry.adk_model, vertex_location=entry.location)


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
