"""The word generator against Vertex AI. Run with `make test-slow`, which loads `.env`."""

import os

import pytest
from conftest import run_in_node

from imposter.utils.text import is_single_word, mentions_word
from imposter.words.generator import WordGenerator

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("GOOGLE_CLOUD_PROJECT"), reason="needs GOOGLE_CLOUD_PROJECT"
    ),
]


async def test_real_generator_gives_a_word_category_and_hint() -> None:
    generator = WordGenerator()

    generated, _ = await run_in_node(
        lambda ctx: generator.generate(ctx=ctx, avoid=["nostalgia", "echo"])
    )

    assert is_single_word(generated.word)
    assert generated.word.lower() not in {"nostalgia", "echo"}
    assert generated.category
    assert not mentions_word(generated.hint, generated.word)
