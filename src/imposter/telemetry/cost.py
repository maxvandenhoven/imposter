from imposter.models.catalog import ModelCatalog, ModelPrice

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


def catalog_cost(
    *,
    catalog: ModelCatalog,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    thinking_tokens: int = 0,
) -> float:
    """Estimate the cost of a model's tokens at its catalog price.

    Args:
        catalog: The models and their prices.
        model_id: The catalog id of the model.
        input_tokens: The prompt tokens.
        output_tokens: The completion tokens.
        thinking_tokens: The thinking tokens.

    Returns:
        The estimated cost in USD, 0 for a model that is not in the catalog, such as a
        fake player.
    """
    if model_id not in {entry.id for entry in catalog.entries}:
        return 0.0

    return estimated_cost(
        price=catalog.entry(model_id).price_per_mtok,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
    )
