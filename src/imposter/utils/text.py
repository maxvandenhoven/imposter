import re

REDACTION = "[redacted]"
"""The text that replaces the secret word in public statements."""

SINGLE_WORD_PATTERN = re.compile(r"[^\W_]+(?:['-][^\W_]+)*")
"""One word: letters or digits with internal hyphens or apostrophes."""

SURROUNDING_PUNCTUATION = " \t\n\"'.,;:!?()[]{}"
"""Characters stripped from both ends of a clue or guess."""


def clean_word(text: str) -> str:
    """Strip whitespace and surrounding punctuation from a one-word answer.

    Args:
        text: The raw answer of a player.

    Returns:
        The answer without leading and trailing whitespace or punctuation.
    """
    return text.strip(SURROUNDING_PUNCTUATION)


def is_single_word(text: str) -> bool:
    """Check whether a cleaned answer is exactly one word.

    Args:
        text: The cleaned answer.

    Returns:
        `True` when the answer is one word of letters or digits, with only internal
        hyphens or apostrophes.
    """
    return SINGLE_WORD_PATTERN.fullmatch(text) is not None


def normalize_word(text: str) -> str:
    """Normalise a word for comparison: clean, lowercase and make simply singular.

    Args:
        text: The word to normalise.

    Returns:
        The normalised word.
    """
    word = clean_word(text).lower()

    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"

    if len(word) > 3 and word.endswith(("ses", "xes", "ches", "shes")):
        return word[:-2]

    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]

    return word


def truncate_words(text: str, cap: int) -> tuple[str, bool]:
    """Cut a text down to at most `cap` words.

    Args:
        text: The text to truncate.
        cap: The maximum number of words.

    Returns:
        The possibly shortened text, stripped of surrounding whitespace, and whether
        words were removed.
    """
    words = text.split()

    if len(words) <= cap:
        return text.strip(), False

    return " ".join(words[:cap]), True


def redact_word(text: str, word: str) -> str:
    """Replace every whole-word occurrence of the secret word in a text.

    Matching ignores case and also catches simple plurals, so a civilian who blurts out
    the word in a public statement cannot leak it to the imposter.

    Args:
        text: The public text.
        word: The secret word.

    Returns:
        The text with each occurrence of the word replaced by `REDACTION`.
    """
    stem = normalize_word(word)
    forms = {clean_word(word).lower(), stem, stem + "s", stem + "es"}

    if stem.endswith("y"):
        forms.add(stem[:-1] + "ies")

    alternatives = "|".join(
        re.escape(form) for form in sorted(forms, key=len, reverse=True)
    )
    pattern = re.compile(rf"\b(?:{alternatives})\b", re.IGNORECASE)

    return pattern.sub(REDACTION, text)


def json_object_text(text: str) -> str:
    """Cut the JSON object out of a model answer that may wrap it in fences or prose.

    Args:
        text: The raw answer of a model.

    Returns:
        The text from the first `{` to the last `}`, or the stripped answer when it has
        no braces, so that parsing it reports the error.
    """
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end < start:
        return text.strip()

    return text[start : end + 1]
