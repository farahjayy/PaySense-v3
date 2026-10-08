"""Plan read-model: total payable is the sum of the real instalments, never a re-derived formula.
First three tests are v1's tests/test_plans.py re-expressed in sen."""

from datetime import date

import pytest

from app.domain.plans import derive_status, enrich_plan, remaining_limit_sen, used_limit_sen


def _instalments(amounts, paid=0):
    return [
        {
            "seq": i + 1,
            "due_date": date(2026, 10 + i, 1) if i < 3 else date(2027, i - 2, 1),
            "amount_sen": amount,
            "is_paid": i < paid,
        }
        for i, amount in enumerate(amounts)
    ]


PLAN = {"id": "p1", "total_price_sen": 14762, "monthly_fee_rate_pct": 1.5, "num_installments": 6}


def test_total_payable_is_the_sum_of_the_instalments_on_a_fee_bearing_plan():
    # 147.62 over 6 months at 1.5%/month: 26.81 x 5 then 26.86 = 160.91 (NOT 147.62 x 1.015)
    enriched = enrich_plan(PLAN, _instalments([2681] * 5 + [2686]), today=date(2026, 9, 1))

    assert enriched["total_payable_sen"] == 16091


def test_total_payable_includes_instalments_already_paid():
    enriched = enrich_plan(PLAN, _instalments([2681] * 5 + [2686], paid=2), today=date(2026, 9, 1))

    assert enriched["total_payable_sen"] == 16091


def test_total_payable_is_exact_in_sen():
    plan = {**PLAN, "total_price_sen": 30, "monthly_fee_rate_pct": 0, "num_installments": 3}

    enriched = enrich_plan(plan, _instalments([10, 10, 10]), today=date(2026, 9, 1))

    assert enriched["total_payable_sen"] == 30


# ------------------------------------------------------------------ v2 read-model details
def test_enrich_adds_counts_and_the_next_due_date_without_mutating_inputs():
    plan = dict(PLAN)
    items = _instalments([100, 100, 100], paid=1)

    enriched = enrich_plan(plan, items, today=date(2026, 9, 1))

    assert enriched["paid_count"] == 1
    assert enriched["remaining_count"] == 2
    assert enriched["next_due_date"] == "2026-11-01"
    assert enriched["installment_amount_sen"] == 100
    assert plan == PLAN and "status" not in plan  # inputs untouched


def test_enrich_orders_instalments_by_seq_and_accepts_iso_date_strings():
    items = [
        {"seq": 2, "due_date": "2026-11-01", "amount_sen": 50, "is_paid": False},
        {"seq": 1, "due_date": "2026-10-01", "amount_sen": 40, "is_paid": True},
    ]

    enriched = enrich_plan(PLAN, items, today=date(2026, 9, 1))

    assert enriched["installment_amount_sen"] == 40
    assert enriched["next_due_date"] == "2026-11-01"


def test_a_plan_without_instalments_is_active_with_nothing_due():
    enriched = enrich_plan(PLAN, [], today=date(2026, 9, 1))

    assert enriched["status"] == "active"
    assert enriched["next_due_date"] is None
    assert enriched["total_payable_sen"] == 0


@pytest.mark.parametrize(
    ("paid", "today", "status"),
    [
        (3, date(2027, 6, 1), "completed"),
        (0, date(2026, 9, 1), "active"),
        (0, date(2026, 10, 2), "overdue"),  # first instalment was due on 1 Oct
        (1, date(2026, 10, 2), "active"),  # paid on time; next due 1 Nov
        (1, date(2026, 11, 2), "overdue"),
    ],
)
def test_derive_status(paid, today, status):
    assert derive_status(_instalments([100, 100, 100], paid=paid), today) == status


def test_an_instalment_due_today_is_not_yet_overdue():
    assert derive_status(_instalments([100]), date(2026, 10, 1)) == "active"


# ------------------------------------------------------------------ provider limits (D-28)
def test_used_limit_is_what_is_still_unpaid():
    items = _instalments([2681] * 5 + [2686], paid=2)

    assert used_limit_sen(items) == 2681 * 3 + 2686


def test_used_limit_of_nothing_or_a_finished_plan_is_zero():
    assert used_limit_sen([]) == 0
    assert used_limit_sen(_instalments([100, 100], paid=2)) == 0


def test_remaining_limit_subtracts_usage_and_floors_at_zero():
    assert remaining_limit_sen(20000, 5000) == 15000
    assert remaining_limit_sen(20000, 25000) == 0


def test_remaining_limit_is_unknown_when_no_limit_is_recorded():
    assert remaining_limit_sen(None, 5000) is None
