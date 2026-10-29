import pytest

from imposter.models.catalog import ModelPrice
from imposter.telemetry.cost import estimated_cost


def test_cost_bills_thinking_as_output() -> None:
    price = ModelPrice(input=2.0, output=10.0)

    cost = estimated_cost(
        price=price, input_tokens=1_000_000, output_tokens=100_000, thinking_tokens=50_000
    )

    assert cost == pytest.approx(3.5)
