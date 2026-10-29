import json

import pytest
from conftest import ReplayLlm
from pydantic import ValidationError

from imposter.models.catalog import ModelCatalogEntry
from imposter.words.generator import WordGenerator
from imposter.words.options import SecretWordResolver, WordMode, WordOptions
from imposter.words.picker import WordPicker


def resolver(*, entry: ModelCatalogEntry, llm: ReplayLlm) -> SecretWordResolver:
    """Build a seeded resolver whose generator replays canned answers."""
    return SecretWordResolver(
        picker=WordPicker.load(seed=5), generator=WordGenerator(entry=entry, model=llm)
    )


async def test_typed_word_keeps_its_category_and_gets_a_hint(
    flash_lite: ModelCatalogEntry, replay_llm: ReplayLlm
) -> None:
    replay_llm.replies = [json.dumps({"hint": "memory"})]
    words = resolver(entry=flash_lite, llm=replay_llm)
    options = WordOptions(mode=WordMode.TYPED, word=" Nostalgia ", category="emotions")

    secret = await words.resolve(options=options, with_hint=True)

    assert (secret.word, secret.category, secret.hint) == (
        "Nostalgia",
        "emotions",
        "memory",
    )
    assert "nostalgia" in words.picker.recent


async def test_random_word_comes_from_the_category_without_a_model_call(
    flash_lite: ModelCatalogEntry, replay_llm: ReplayLlm
) -> None:
    words = resolver(entry=flash_lite, llm=replay_llm)
    options = WordOptions(category="sounds")

    secret = await words.resolve(options=options, with_hint=False)

    assert secret.word in words.picker.category("sounds").words
    assert (secret.category, secret.hint) == ("sounds", None)
    assert replay_llm.requests == []


async def test_generated_word_returns_word_category_and_hint(
    flash_lite: ModelCatalogEntry, replay_llm: ReplayLlm
) -> None:
    replay_llm.replies = [
        json.dumps({"word": "dusk", "category": "times of day", "hint": "fading"})
    ]
    words = resolver(entry=flash_lite, llm=replay_llm)

    secret = await words.resolve(
        options=WordOptions(mode=WordMode.GENERATED), with_hint=True
    )

    assert (secret.word, secret.category, secret.hint) == (
        "dusk",
        "times of day",
        "fading",
    )
    assert len(replay_llm.requests) == 1


async def test_hint_that_gives_the_word_away_is_rejected(
    flash_lite: ModelCatalogEntry, replay_llm: ReplayLlm
) -> None:
    replay_llm.replies = [json.dumps({"hint": "echoes"})]
    words = resolver(entry=flash_lite, llm=replay_llm)
    options = WordOptions(mode=WordMode.TYPED, word="echo")

    with pytest.raises(ValueError, match="gives the secret word away"):
        await words.resolve(options=options, with_hint=True)


async def test_hints_need_a_generator() -> None:
    words = SecretWordResolver(picker=WordPicker.load(seed=5), generator=None)

    with pytest.raises(ValueError, match="need a word generator"):
        await words.resolve(options=WordOptions(), with_hint=True)


@pytest.mark.parametrize(
    "options",
    [
        {"mode": "typed"},
        {"mode": "typed", "word": "two words"},
        {"mode": "random", "word": "echo"},
    ],
)
def test_invalid_word_options_are_rejected(options: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        WordOptions.model_validate(options)
