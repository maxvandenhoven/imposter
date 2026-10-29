from imposter.judge.base import JudgeVerdict
from imposter.utils.text import normalize_word

CODE_JUDGE = "code"
"""The `judge_model` of verdicts decided by the code checks."""

MIN_SUBSTRING_LENGTH = 3
"""The shortest word that counts when it appears inside the other word."""

MIN_STEM_LENGTH = 5
"""The shortest shared beginning that counts as a shared stem."""

MIN_STEM_SHARE = 0.7
"""The part of the shorter word a shared stem must cover."""


def shared_prefix_length(first: str, second: str) -> int:
    """Count the letters two words share at their beginning.

    Args:
        first: The first word.
        second: The second word.

    Returns:
        The length of the common prefix.
    """
    length = 0

    for left, right in zip(first, second, strict=False):
        if left != right:
            break

        length += 1

    return length


def same_word_check(guess: str, word: str) -> JudgeVerdict | None:
    """Decide a guess in code when it matches after normalisation.

    Args:
        guess: The guess of an imposter.
        word: The secret word.

    Returns:
        A positive verdict for a match such as `Cats` for `cat`, or `None` when only a
        model can decide, for example `couch` for `sofa`.
    """
    if normalize_word(guess) != normalize_word(word):
        return None

    return JudgeVerdict(
        verdict=True,
        confidence=1.0,
        rationale="The guess matches the word after normalisation.",
        judge_model=CODE_JUDGE,
    )


def clue_check(clue: str, word: str) -> JudgeVerdict | None:
    """Reject a clue in code when it is a form of the word or shares its stem.

    Args:
        clue: The one-word clue.
        word: The secret word.

    Returns:
        A negative verdict for a match, a word inside the other (`firefighter` for
        `fire`) or a shared stem (`nostalgic` for `nostalgia`), or `None` when only a
        model can decide.
    """
    clue_form, word_form = normalize_word(clue), normalize_word(word)
    shorter = min(len(clue_form), len(word_form))
    stem = shared_prefix_length(clue_form, word_form)
    rationale = None

    if clue_form == word_form:
        rationale = "The clue is the word after normalisation."
    elif shorter >= MIN_SUBSTRING_LENGTH and (
        clue_form in word_form or word_form in clue_form
    ):
        rationale = "One of the clue and the word contains the other."
    elif stem >= MIN_STEM_LENGTH and stem >= MIN_STEM_SHARE * shorter:
        rationale = "The clue shares its stem with the word."

    if rationale is None:
        return None

    return JudgeVerdict(
        verdict=False, confidence=1.0, rationale=rationale, judge_model=CODE_JUDGE
    )
