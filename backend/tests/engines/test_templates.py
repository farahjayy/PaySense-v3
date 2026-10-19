"""Factor sentences: one per feature, and every number in a sentence comes from the feature values.

The expectations below are written out independently of the templates (plain arithmetic on the
feature values), so a template that shows a number from anywhere else fails here.
"""

import re

import pytest

from app.engines.risk.features import FEATURE_NAMES
from app.engines.risk.templates import TEMPLATES, render_factor

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def half_up(x: float) -> int:
    return int(abs(x) + 0.5)


def figures_in(text: str) -> list[str]:
    return [m.replace(",", "") for m in NUMBER.findall(text)]


VALUES = {
    "disc_weekly_p50": 84.6,
    "disc_weekly_p90": 140.2,
    "disc_volatility": 31.4,
    "margin_monthly_p50_without": 120.4,
    "margin_cum_p10_without": -310.5,
    "income_p10_monthly": 410.0,
    "instalment_amount": 100.0,
    "num_instalments": 12.0,
    "monthly_fee_rate": 1.5,
    "instalment_to_income": 0.254,
    "dsr_with_purchase": 0.4,
    "active_plans_with_purchase": 3.0,
    "bnpl_outstanding_to_income": 1.84,
    "upfront_to_income": 0.2,
    "limit_utilisation_with_purchase": 0.9,
    "limit_known": 0.0,
    "savings_buffer_to_outgoings": 0.42,
}

EXPECTED = {
    "disc_weekly_p50": [str(half_up(84.6))],
    "disc_weekly_p90": [str(half_up(140.2))],
    "disc_volatility": [str(half_up(31.4))],
    "margin_monthly_p50_without": [str(half_up(120.4))],
    "margin_cum_p10_without": [str(half_up(-310.5))],
    "income_p10_monthly": [str(half_up(410.0))],
    "instalment_amount": [str(half_up(100.0))],
    "num_instalments": ["12"],
    "monthly_fee_rate": ["1.5"],
    "instalment_to_income": [str(half_up(0.254 * 100))],
    "dsr_with_purchase": [str(half_up(0.4 * 100))],
    "active_plans_with_purchase": ["3"],
    "bnpl_outstanding_to_income": ["1.8"],
    "upfront_to_income": [str(half_up(0.2 * 100))],
    "limit_utilisation_with_purchase": [str(half_up(0.9 * 100))],
    "limit_known": [],
    "savings_buffer_to_outgoings": ["0.4"],
}


def test_every_feature_has_a_template():
    assert set(TEMPLATES) == set(FEATURE_NAMES)


@pytest.mark.parametrize("name", FEATURE_NAMES)
def test_every_number_in_a_sentence_is_a_function_of_the_feature_values(name):
    factor = render_factor(name, VALUES)
    assert factor is not None
    assert factor.feature == name
    assert figures_in(factor.text) == EXPECTED[name]
    assert list(factor.figures) == EXPECTED[name]


@pytest.mark.parametrize("name", FEATURE_NAMES)
def test_sentences_end_with_a_full_stop_and_name_no_other_feature(name):
    text = render_factor(name, VALUES).text
    assert text.endswith(".")
    assert "_" not in text  # never a raw feature name


def test_changing_a_value_changes_the_number_shown():
    low = render_factor("instalment_amount", {**VALUES, "instalment_amount": 50.0})
    high = render_factor("instalment_amount", {**VALUES, "instalment_amount": 250.0})
    assert figures_in(low.text) == ["50"]
    assert figures_in(high.text) == ["250"]


def test_negative_margins_are_worded_as_a_shortfall_with_the_size_of_the_gap():
    short = render_factor(
        "margin_monthly_p50_without", {**VALUES, "margin_monthly_p50_without": -80.0}
    )
    assert "short" in short.text
    assert figures_in(short.text) == ["80"]
    left = render_factor("margin_monthly_p50_without", VALUES)
    assert "left" in left.text


def test_thousands_use_separators_and_negative_money_keeps_its_sign():
    big = render_factor("income_p10_monthly", {**VALUES, "income_p10_monthly": 1234.4})
    assert "RM 1,234" in big.text
    assert "-RM 311" in render_factor("margin_cum_p10_without", VALUES).text


def test_few_instalments_are_explained_differently_from_many():
    few = render_factor("num_instalments", {**VALUES, "num_instalments": 3.0})
    many = render_factor("num_instalments", VALUES)
    assert "larger" in few.text
    assert "longer" in many.text


def test_limit_known_only_speaks_when_no_limit_is_recorded():
    assert render_factor("limit_known", {**VALUES, "limit_known": 1.0}) is None
    assert "not recorded" in render_factor("limit_known", VALUES).text


def test_a_feature_missing_from_the_values_is_an_error_not_a_guess():
    values = {k: v for k, v in VALUES.items() if k != "instalment_amount"}
    with pytest.raises(KeyError):
        render_factor("instalment_amount", values)
    with pytest.raises(KeyError):
        render_factor("not_a_feature", VALUES)


def test_a_single_plan_or_instalment_reads_naturally():
    plans = render_factor("active_plans_with_purchase", {**VALUES, "active_plans_with_purchase": 1})
    assert "only BNPL plan" in plans.text and "1 active" not in plans.text
    steps = render_factor("num_instalments", {**VALUES, "num_instalments": 1})
    assert "1 instalments" not in steps.text and "single payment" in steps.text


def test_a_value_that_is_not_a_finite_number_is_refused_not_printed():
    import math

    for bad in (math.nan, math.inf):
        with pytest.raises(ValueError, match="finite"):
            render_factor("disc_weekly_p50", {**VALUES, "disc_weekly_p50": bad})


def test_no_savings_buffer_is_said_without_a_number():
    factor = render_factor(
        "savings_buffer_to_outgoings", {**VALUES, "savings_buffer_to_outgoings": 0.0}
    )
    assert figures_in(factor.text) == [] and factor.figures == ()
    assert "savings" in factor.text


def test_the_savings_reason_counts_months_of_outgoings_not_income():
    factor = render_factor("savings_buffer_to_outgoings", VALUES)
    assert "months of your usual spending and bills" in factor.text
    assert "income" not in factor.text
