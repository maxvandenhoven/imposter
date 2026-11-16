import json

import pytest
from conftest import ReplayLlm, run_in_node

from imposter.models.catalog import ModelCatalogEntry
from imposter.words import generator as generator_module
from imposter.words.generator import WordGenerator


async def test_generate_avoids_recent_words(
    flash_lite: ModelCatalogEntry, replay_llm: ReplayLlm
) -> None:
    replay_llm.replies = [
        json.dumps({"word": "dusk", "category": "times of day", "hint": "fading"})
    ]
    generator = WordGenerator(entry=flash_lite, model=replay_llm)

    generated, events = await run_in_node(
        lambda ctx: generator.generate(ctx=ctx, avoid=["echo", "awe"])
    )

    assert (generated.word, generated.category, generated.hint) == (
        "dusk",
        "times of day",
        "fading",
    )
    assert "awe, echo" in replay_llm.prompt()
    assert "word_generator" in {event.author for event in events}


async def test_hint_for_a_known_word(
    flash_lite: ModelCatalogEntry, replay_llm: ReplayLlm
) -> None:
    replay_llm.replies = [json.dumps({"hint": "memory"})]
    generator = WordGenerator(entry=flash_lite, model=replay_llm)

    hint, _ = await run_in_node(
        lambda ctx: generator.hint(ctx=ctx, word="nostalgia", category="emotions")
    )

    assert hint == "memory"
    assert "Secret word: nostalgia" in replay_llm.prompt()


async def test_answer_that_misses_the_schema_is_asked_again_by_adk(
    flash_lite: ModelCatalogEntry, replay_llm: ReplayLlm, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(generator_module.GENERATOR_RETRY, "initial_delay", 0.0)
    replay_llm.replies = ["no json", json.dumps({"hint": "memory"})]
    generator = WordGenerator(entry=flash_lite, model=replay_llm)

    hint, _ = await run_in_node(
        lambda ctx: generator.hint(ctx=ctx, word="nostalgia", category=None)
    )

    assert hint == "memory"
    assert len(replay_llm.requests) == 2
