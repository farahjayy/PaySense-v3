"""The risk check: plumbing between the plan rules, both simulations, the features and the model.

A stub predictor stands in for the trained model, so these tests are about what is passed in and
what comes back, not about model quality.
"""

from datetime import date

import pytest

from app.domain.plan_builder import ProposalError
from app.engines.forecasting.models import MovingAverage
from app.engines.risk.check import RiskRequest, remaining_limit, run_check
from app.engines.risk.features import FEATURE_NAMES
from tests.engines.test_summary import EXISTING, ITEMS, TODAY, ledger


class StubPredictor:
    version = "stub-1"
    feature_schema_hash = "stub-hash"

    def __init__(self, p: float = 0.2):
        self.p = p
        self.seen: list[list[float]] = []

    def predict(self, vector):
        self.seen.append(list(vector))
        return self.p

    def contributions(self, vector):
        return [0.0] * len(vector)


def request(**overrides) -> RiskRequest:
    fields = dict(
        provider="spaylater",
        item_name="Headphones",
        purchase_date=TODAY,
        num_installments=3,
        total_price_sen=60000,
    )
    fields.update(overrides)
    return RiskRequest(**fields)


def check(predictor=None, req=None, rows=None, plans=EXISTING, limits=None, **kw):
    return run_check(
        rows=ledger() if rows is None else rows,
        items=ITEMS,
        plans=plans,
        provider_limits={"spaylater": 300000} if limits is None else limits,
        request=req or request(),
        today=TODAY,
        forecaster=MovingAverage(8),
        predictor=predictor or StubPredictor(),
        paths=200,
        seed=3,
        **kw,
    )


def test_the_predictor_sees_all_seventeen_features_in_the_declared_order():
    stub = StubPredictor()
    result = check(stub)

    assert result.status == "ok"
    assert len(stub.seen) == 1 and len(stub.seen[0]) == len(FEATURE_NAMES) == 17
    assert list(result.features) == list(FEATURE_NAMES)
    assert stub.seen[0] == [result.features[name] for name in FEATURE_NAMES]


def test_the_shown_probability_comes_from_the_model_and_the_simulated_one_is_kept_beside_it():
    result = check(StubPredictor(0.05))

    assert result.probability == 0.05
    assert result.band == "Safe"
    assert result.score == 95
    assert result.p_simulated >= result.p_without  # a purchase never makes things better
    assert result.gap == pytest.approx(result.probability - result.p_simulated)
    assert result.predictor_version == "stub-1"


@pytest.mark.parametrize(
    ("p", "band"),
    [(0.0, "Safe"), (0.099, "Safe"), (0.1, "Caution"), (0.299, "Caution"), (0.3, "At Risk")],
)
def test_bands_use_the_pre_registered_thresholds(p, band):
    assert check(StubPredictor(p)).band == band


def test_curves_for_the_chart_cover_the_same_months_with_and_without_the_purchase():
    result = check()
    with_plan, without = result.with_plan_curve, result.without_curve

    assert with_plan.months == without.months and len(with_plan.months) >= 3
    for curve in (with_plan, without):
        n = len(curve.months)
        assert len(curve.cumulative_p10_sen) == len(curve.cumulative_p50_sen) == n
        assert len(curve.cumulative_p90_sen) == n
    # buying something can only lower the running margin
    assert with_plan.cumulative_p50_sen[-1] <= without.cumulative_p50_sen[-1]


def test_a_ledger_that_is_too_short_returns_a_refusal_not_a_number():
    stub = StubPredictor()
    result = check(stub, rows=ledger()[:3])

    assert result.status == "locked"
    assert result.lock_reason in ("needs_four_months", "no_usable_history")
    assert result.probability is None and result.band is None and result.features is None
    assert stub.seen == []  # the model is never asked


def test_the_same_inputs_give_the_same_answer():
    a, b = check(), check()
    assert a.p_simulated == b.p_simulated
    assert a.features == b.features
    assert a.with_plan_curve == b.with_plan_curve


def test_the_recorded_limit_caps_what_is_financed_and_the_rest_is_paid_at_checkout():
    # SPayLater limit RM3,000 with RM200 of existing unpaid instalments leaves RM2,800
    assert remaining_limit("spaylater", {"spaylater": 300000}, EXISTING) == 280000
    result = check(req=request(total_price_sen=400000), limits={"spaylater": 300000})

    assert result.proposal.financed_sen == 280000
    assert result.proposal.upfront_sen == 120000
    assert result.features["upfront_to_income"] > 0


def test_a_provider_with_no_recorded_limit_is_not_capped_and_says_so_in_the_features():
    assert remaining_limit("atome", {}, EXISTING) is None
    result = check(req=request(provider="atome", num_installments=4), limits={})

    assert result.proposal.upfront_sen == 0
    assert result.features["limit_known"] == 0.0


def test_the_other_provider_path_ignores_limits():
    assert remaining_limit("other", {"other": 100}, EXISTING) is None


def test_a_request_the_plan_rules_reject_raises_their_error():
    with pytest.raises(ProposalError) as err:
        check(req=request(num_installments=99))
    assert err.value.code == "invalid_instalments"


def test_data_quality_notes_from_the_forecast_are_passed_through():
    old = [r for r in ledger() if r["date"] < date(2025, 4, 1)]  # ledger stops at the end of March
    result = check(rows=old)

    assert result.status == "ok"
    assert result.stale_days is not None and result.stale_days > 14
