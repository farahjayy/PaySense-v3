"""The author's own scenarios through the whole risk check with the real model and forecaster.

A RM600 purchase split over three months is Safe on RM2,000 a month, At Risk on RM500 a month,
and At Risk with savings only and no income (PRD section 6). Two more: a steady surplus with a small
purchase is Safe, and a monthly deficit with a large purchase is At Risk.
"""

import pytest

from app.engines.forecasting.serving import served_forecaster
from app.engines.risk.artefact import MODEL_ROOT, load_if_present
from app.engines.risk.check import RiskRequest, run_check
from tests.engines.test_designed_cases import TODAY, items, ledger

pytestmark = pytest.mark.skipif(
    not (MODEL_ROOT / "v2" / "metadata.json").exists(), reason="no risk model exported yet"
)


@pytest.fixture(scope="module")
def predictor():
    return load_if_present()


def check(predictor, income_sen, price_sen=60000, instalments=3):
    return run_check(
        rows=ledger(income_sen),
        items=items(income_sen),
        plans=[],
        provider_limits={},
        request=RiskRequest(
            provider="spaylater",
            item_name="Headphones",
            purchase_date=TODAY,
            num_installments=instalments,
            total_price_sen=price_sen,
        ),
        today=TODAY,
        forecaster=served_forecaster(),
        predictor=predictor,
        seed=7,
    )


def test_rm600_over_three_months_is_safe_on_rm2000_a_month(predictor):
    result = check(predictor, 200000)
    assert result.status == "ok" and result.band == "Safe", (result.probability, result.p_simulated)


def test_the_same_purchase_is_at_risk_on_rm500_a_month(predictor):
    result = check(predictor, 50000)
    assert result.band == "At Risk", (result.probability, result.p_simulated)


def test_with_savings_only_and_no_income_the_purchase_is_at_risk(predictor):
    result = check(predictor, 0)
    assert result.status == "ok" and result.band == "At Risk", (
        result.probability,
        result.p_simulated,
    )


def test_a_steady_surplus_and_a_small_purchase_is_safe(predictor):
    result = check(predictor, 200000, price_sen=10000, instalments=2)
    assert result.band == "Safe", (result.probability, result.p_simulated)


def test_a_monthly_deficit_and_a_large_purchase_is_at_risk(predictor):
    result = check(predictor, 50000, price_sen=300000, instalments=6)
    assert result.band == "At Risk", (result.probability, result.p_simulated)


@pytest.mark.parametrize("income", [200000, 50000, 0])
def test_the_model_and_the_direct_simulation_agree_on_the_band_in_the_designed_cases(
    predictor, income
):
    from app.engines.forecasting.simulate import band

    result = check(predictor, income)
    assert result.band == band(result.p_simulated)
    assert abs(result.gap) < 0.15, (result.probability, result.p_simulated)
