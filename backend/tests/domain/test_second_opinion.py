"""D-57: the Second-Opinion Check's pure parts — stacked dues, exposure, the added chance."""

from datetime import date

import pytest

from app.domain.second_opinion import (
    BNM_LIMIT_LINE_SEN,
    added_probability,
    exposure,
    stack_dues,
)

TODAY = date(2026, 1, 10)


def plan(provider, label, dues):
    return {
        "id": f"p-{provider}",
        "provider": provider,
        "provider_label": label,
        "installments": [
            {"seq": i + 1, "due_date": d, "amount_sen": a, "is_paid": paid}
            for i, (d, a, paid) in enumerate(dues)
        ],
    }


PLANS = [
    plan("spaylater", "SPayLater", [("2025-12-15", 5000, True), ("2026-01-15", 5000, False),
                                    ("2026-02-15", 5000, False)]),
    plan("atome", "Atome", [("2026-01-05", 3000, False), ("2026-02-05", 3000, False)]),
]  # fmt: skip
NEW = [(date(2026, 2, 20), 26633), (date(2026, 3, 20), 26633), (date(2026, 4, 20), 26634)]


def test_dues_are_stacked_by_month_and_provider_with_the_new_plan_and_known_income():
    months = stack_dues(PLANS, NEW, {"2026-02": 120000}, TODAY)
    assert [m.month for m in months] == ["2026-01", "2026-02", "2026-03", "2026-04"]
    jan, feb, mar, _ = months
    # unpaid and overdue (5 Jan, before today) is still owed: it sits in the current month
    assert dict(jan.by_provider) == {"Atome": 3000, "SPayLater": 5000}
    assert jan.new_plan_sen == 0 and jan.total_sen == 8000
    assert dict(feb.by_provider) == {"Atome": 3000, "SPayLater": 5000}
    assert feb.new_plan_sen == 26633 and feb.total_sen == 34633
    assert feb.known_income_sen == 120000
    assert mar.by_provider == () and mar.total_sen == 26633 and mar.known_income_sen == 0


def test_paid_instalments_are_never_counted():
    months = stack_dues(PLANS, NEW, {}, TODAY)
    assert all(m.month != "2025-12" for m in months)
    assert sum(m.total_sen for m in months) == 3000 + 5000 + 3000 + 5000 + 26633 * 2 + 26634


def test_a_new_plan_backdated_into_an_earlier_month_is_owed_this_month():
    """Review finding 4: a purchase dated in the past can have instalments already due."""
    backdated = [(date(2025, 12, 25), 5000), (date(2026, 1, 25), 5000), (date(2026, 2, 25), 5000)]
    months = stack_dues([], backdated, {}, TODAY)
    assert [m.month for m in months] == ["2026-01", "2026-02"]
    assert months[0].new_plan_sen == 10000
    assert sum(m.new_plan_sen for m in months) == 15000


def test_exposure_before_and_after_across_providers():
    out = exposure(PLANS, 79900, "SPayLater", {"spaylater": 100000, "atome": 60000})
    assert out.unpaid_before_sen == 16000 and out.unpaid_after_sen == 16000 + 79900
    assert out.providers_before == ("Atome", "SPayLater")
    assert out.plans_before == 2 and out.plans_after == 3
    assert out.recorded_limits_sen == 160000
    assert out.reaches_bnm_line is True  # RM1,600 of recorded limits >= RM1,500


def test_the_bnm_line_is_unknown_when_no_limit_was_recorded():
    out = exposure(PLANS, 79900, "SPayLater", {"spaylater": None, "atome": None})
    assert out.recorded_limits_sen is None and out.reaches_bnm_line is None
    assert BNM_LIMIT_LINE_SEN == 150_000


@pytest.mark.parametrize(
    ("with_", "without", "added"),
    [(0.42, 0.30, 0.12), (1.0, 1.0, 0.0), (0.2, 0.25, 0.0), (None, 0.3, None), (0.3, None, None)],
)
def test_the_added_chance_is_with_minus_without_never_negative(with_, without, added):
    got = added_probability(with_, without)
    assert got == (pytest.approx(added) if added is not None else None)
