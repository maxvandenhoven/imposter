import json

from conftest import ReplayLlm

from imposter.models.catalog import ModelCatalogEntry
from imposter.words.generator import WordGenerator


async def test_generate_avoids_recent_words(
    flash_lite: ModelCatalogEntry, replay_llm: ReplayLlm
) -> None:
    replay_llm.replies = [
        json.dumps({"word": "dusk", "category": "times of day", "hint": "fading"})
    ]
    generator = WordGenerator(entry=flash_lite, model=replay_llm)

    generated = await generator.generate(["echo", "awe"])

    assert (generated.word, generated.category, generated.hint) == (
        "dusk",
        "times of day",
        "fading",
    )
    assert "awe, echo" in replay_llm.prompt()


async def test_hint_for_a_known_word(
    flash_lite: ModelCatalogEntry, replay_llm: ReplayLlm
) -> None:
    replay_llm.replies = [json.dumps({"hint": "memory"})]
    generator = WordGenerator(entry=flash_lite, model=replay_llm)

    hint = await generator.hint(word="nostalgia", category="emotions")

    assert hint == "memory"
    assert "Secret word: nostalgia" in replay_llm.prompt()
