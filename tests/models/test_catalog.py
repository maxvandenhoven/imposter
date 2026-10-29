from pathlib import Path

import pytest

from imposter.models.catalog import (
    ModelCatalog,
    ModelCatalogEntry,
    ModelPrice,
    ModelProvider,
    ModelThinking,
    ModelVia,
)


def entry(model_id: str) -> ModelCatalogEntry:
    """Build a minimal catalog entry."""
    return ModelCatalogEntry(
        id=model_id,
        display_name=model_id.title(),
        provider=ModelProvider.GOOGLE,
        adk_model=model_id,
        via=ModelVia.NATIVE,
        price_per_mtok=ModelPrice(input=1, output=2),
    )


def test_built_in_catalog_has_gemini_and_claude_models() -> None:
    catalog = ModelCatalog.load()
    providers = {entry.provider for entry in catalog.entries}

    assert {ModelProvider.GOOGLE, ModelProvider.ANTHROPIC} <= providers
    assert catalog.entry("gemini-flash-lite").via is ModelVia.NATIVE
    assert all(
        entry.adk_model.startswith("vertex_ai/")
        for entry in catalog.entries
        if entry.via is ModelVia.LITELLM
    )


def test_load_reads_yaml_with_defaults(tmp_path: Path) -> None:
    path = tmp_path / "catalog.yaml"
    path.write_text(
        "- id: m\n  display_name: M\n  provider: qwen\n  adk_model: vertex_ai/qwen/m\n"
        '  via: litellm\n  thinking: "high"\n'
        "  price_per_mtok: {input: 0.1, output: 0.2}\n"
    )

    loaded = ModelCatalog.load(path).entry("m")

    assert loaded.thinking is ModelThinking.HIGH
    assert loaded.location == "global"
    assert loaded.supports_structured_output is False


def test_entry_raises_for_unknown_ids() -> None:
    with pytest.raises(KeyError, match="no model with id 'nope'"):
        ModelCatalog([entry("a")]).entry("nope")


def test_catalog_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="duplicate ids: a"):
        ModelCatalog([entry("a"), entry("b"), entry("a")])
