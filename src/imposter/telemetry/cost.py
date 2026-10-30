from imposter.models.catalog import ModelPrice

TOKENS_PER_PRICE_UNIT = 1_000_000
"""Catalog prices are per million tokens."""


def estimated_cost(
    *, price: ModelPrice, input_tokens: int, output_tokens: int, thinking_tokens: int = 0
) -> float:
    """Estimate the cost of a model's tokens, with thinking billed as output.

    Args:
        price: The catalog price of the model.
        input_tokens: The prompt tokens.
        output_tokens: The completion tokens.
        thinking_tokens: The thinking tokens.

    Returns:
        The estimated cost in USD.
    """
    billed = input_tokens * price.input + (output_tokens + thinking_tokens) * price.output

    return billed / TOKENS_PER_PRICE_UNIT
