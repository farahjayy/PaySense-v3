"""Choosing which reasons to show: only features that push risk up by at least 0.02."""

import pytest

from app.engines.risk.explain import FACTOR_THRESHOLD, MAX_FACTORS, select_factors
from app.engines.risk.features import FEATURE_NAMES

VALUES = {
    "disc_weekly_p50": 80.0,
    "disc_weekly_p90": 140.0,
    "disc_volatility": 30.0,
    "margin_monthly_p50_without": 120.0,
    "margin_cum_p10_without": -300.0,
    "income_p10_monthly": 410.0,
    "instalment_amount": 100.0,
    "num_instalments": 12.0,
    "monthly_fee_rate": 1.5,
    "instalment_to_income": 0.25,
    "dsr_with_purchase": 0.4,
    "active_plans_with_purchase": 3.0,
    "bnpl_outstanding_to_income": 1.8,
    "upfront_to_income": 0.2,
    "limit_utilisation_with_purchase": 0.9,
    "limit_known": 0.0,
    "savings_buffer_to_income": 0.0,
}


def contributions(**named: float) -> list[float]:
    return [named.get(name, 0.0) for name in FEATURE_NAMES]


def test_only_contributions_at_or_above_the_threshold_are_shown():
    assert FACTOR_THRESHOLD == 0.02
    out = select_factors(
        VALUES,
        contributions(instalment_amount=0.0199, dsr_with_purchase=0.02, monthly_fee_rate=0.5),
    )
    assert [f.feature for f in out] == ["monthly_fee_rate", "dsr_with_purchase"]


def test_factors_that_lower_risk_are_never_listed_as_reasons():
    out = select_factors(VALUES, contributions(instalment_amount=-0.3, dsr_with_purchase=0.05))
    assert [f.feature for f in out] == ["dsr_with_purchase"]


def test_largest_first_and_at_most_five():
    assert MAX_FACTORS == 5
    weights = {name: 0.03 + i / 100 for i, name in enumerate(FEATURE_NAMES[:8])}
    out = select_factors(VALUES, contributions(**weights))

    assert len(out) == 5
    assert [f.contribution for f in out] == sorted((f.contribution for f in out), reverse=True)
    assert out[0].feature == FEATURE_NAMES[7]


def test_nothing_qualifying_gives_an_empty_list_for_the_nothing_stands_out_message():
    assert select_factors(VALUES, contributions(dsr_with_purchase=0.01)) == []
    assert select_factors(VALUES, [0.0] * len(FEATURE_NAMES)) == []


def test_a_sentence_can_only_mention_a_feature_that_passed_the_threshold():
    weights = {"dsr_with_purchase": 0.1, "instalment_amount": 0.01}
    out = select_factors(VALUES, contributions(**weights))
    text = " ".join(f.text for f in out)
    assert "RM 100" not in text  # the instalment amount did not pass
    assert "40%" in text


def test_a_feature_whose_template_has_nothing_to_say_is_skipped_without_using_a_slot():
    values = {**VALUES, "limit_known": 1.0}  # a recorded limit: the template stays silent
    out = select_factors(values, contributions(limit_known=0.5, dsr_with_purchase=0.04))
    assert [f.feature for f in out] == ["dsr_with_purchase"]


def test_figures_and_the_contribution_are_carried_for_the_report():
    (factor,) = select_factors(VALUES, contributions(dsr_with_purchase=0.07))
    assert factor.figures == ("40",)
    assert factor.contribution == pytest.approx(0.07)


def test_a_contribution_vector_of_the_wrong_length_is_an_error_not_a_misalignment():
    with pytest.raises(ValueError, match="17"):
        select_factors(VALUES, [0.1] * 15)
