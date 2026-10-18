"""G1 (engine v3, D-62): a two-part model gives q; the shown probability is b + (1 - b) * q with b
the request's own simulation without the purchase, and the reasons are about the purchase."""

import pytest

from app.engines.forecasting.models import MovingAverage
from app.engines.risk.assess import assess
from app.engines.risk.check import compose, is_two_part
from tests.engines.test_check import StubPredictor, check, request
from tests.engines.test_summary import EXISTING, ITEMS, TODAY, ledger


class TwoPartStub(StubPredictor):
    target = "two_part"

    def contributions(self, vector):
        return [0.1] + [0.0] * (len(vector) - 1)


def test_compose_puts_the_added_share_on_top_of_the_base():
    assert compose(0.4, 0.5) == pytest.approx(0.7)
    assert compose(1.0, 0.3) == 1.0 and compose(0.0, 0.3) == pytest.approx(0.3)
    assert compose(0.2, 1.2) == 1.0 and compose(0.2, -0.1) == pytest.approx(0.2)


def test_a_predictor_without_a_target_is_a_direct_one():
    assert not is_two_part(StubPredictor())
    assert is_two_part(TwoPartStub())


def test_the_shown_probability_is_composed_on_the_simulated_base():
    result = check(TwoPartStub(0.5))
    assert result.status == "ok"
    expected = result.p_without + (1 - result.p_without) * 0.5
    assert result.probability == pytest.approx(expected)
    assert result.probability >= result.p_without


def test_a_direct_predictor_is_shown_unchanged():
    assert check(StubPredictor(0.05)).probability == 0.05


def test_two_part_reasons_are_scaled_to_the_shown_scale():
    found = assess(
        ledger(), ITEMS, EXISTING, {"spaylater": 300000}, request(), TODAY, MovingAverage(8),
        TwoPartStub(0.5), seed=3, paths=150,
    )  # fmt: skip
    b = found.result.p_without
    expected = 0.1 * (1 - b)
    if expected >= 0.02:
        assert found.factors and found.factors[0].contribution == pytest.approx(expected)
    else:
        assert not found.factors
