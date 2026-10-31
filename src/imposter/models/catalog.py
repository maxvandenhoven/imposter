from enum import StrEnum
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

CATALOG_PATH = Path(__file__).with_name("catalog.yaml")
"""The built-in model catalog."""


class ModelProvider(StrEnum):
    """The company or community that publishes a model."""

    GOOGLE = "google"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    META = "meta"
    QWEN = "qwen"
    DEEPSEEK = "deepseek"
    MISTRAL = "mistral"


class ModelVia(StrEnum):
    """How ADK calls a model: natively for Gemini, through LiteLLM for the others."""

    NATIVE = "native"
    LITELLM = "litellm"


class ModelThinking(StrEnum):
    """How much native thinking a model does, off by default (README D26)."""

    OFF = "off"
    LOW = "low"
    HIGH = "high"


class ModelPrice(BaseModel):
    """The price of a model in USD per million tokens, for cost estimates.

    Attributes:
        input: The price of a million prompt tokens.
        output: The price of a million completion and thinking tokens.
    """

    model_config = ConfigDict(frozen=True)

    input: float = Field(ge=0)
    output: float = Field(ge=0)


class ModelCatalogEntry(BaseModel):
    """One model that can play a seat.

    Attributes:
        id: The catalog id, used in `PlayerConfig.model_id`.
        display_name: The name shown in the UI and in `models` identity mode.
        provider: The publisher of the model.
        adk_model: The model string ADK gets: a Gemini model id for native models, a
            LiteLLM model string such as `vertex_ai/claude-...` otherwise.
        via: How ADK calls the model.
        location: The Vertex AI location to call, `global` or a region.
        logo: The path of the logo, relative to the web assets.
        supports_structured_output: Whether the model takes a response schema, otherwise
            the prompt asks for JSON.
        thinking: How much native thinking the model does.
        always_reasons: Whether the model reasons by default and takes a reasoning
            effort, so that `thinking` is sent to it as one (`off` becomes the lowest
            effort). Only for models called through LiteLLM.
        temperature: The default sampling temperature.
        price_per_mtok: The price per million tokens.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    provider: ModelProvider
    adk_model: str = Field(min_length=1)
    via: ModelVia
    location: str = "global"
    logo: str | None = None
    supports_structured_output: bool = False
    thinking: ModelThinking = ModelThinking.OFF
    always_reasons: bool = False
    temperature: float = Field(default=1.0, ge=0, le=2)
    price_per_mtok: ModelPrice


class ModelCatalog:
    """The models that can play a seat, looked up by catalog id.

    Attributes:
        entries: The entries in catalog order.
    """

    def __init__(self, entries: list[ModelCatalogEntry]) -> None:
        """Initialize the catalog.

        Args:
            entries: The entries in catalog order.

        Raises:
            ValueError: When two entries share an id.
        """
        ids = [entry.id for entry in entries]
        duplicates = sorted({model_id for model_id in ids if ids.count(model_id) > 1})

        if duplicates:
            message = f"The model catalog has duplicate ids: {', '.join(duplicates)}."
            raise ValueError(message)

        self.entries = entries

    @classmethod
    def load(cls, path: Path = CATALOG_PATH) -> Self:
        """Load a catalog from a YAML file with a list of entries.

        Args:
            path: The YAML file, the built-in catalog by default.

        Returns:
            The catalog.
        """
        data = yaml.safe_load(path.read_text())
        entries = TypeAdapter(list[ModelCatalogEntry]).validate_python(data)

        return cls(entries)

    def entry(self, model_id: str) -> ModelCatalogEntry:
        """Look up an entry by catalog id.

        Args:
            model_id: The catalog id.

        Returns:
            The entry.

        Raises:
            KeyError: When no entry has the id.
        """
        for entry in self.entries:
            if entry.id == model_id:
                return entry

        message = f"The model catalog has no model with id {model_id!r}."
        raise KeyError(message)
