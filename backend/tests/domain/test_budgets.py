"""Budgets (WP2): status on the month summary's definition of spent, and the suggestion's
arithmetic, checked against hand-computed numbers."""

from datetime import date

import pytest

from app.domain import budgets as b
from app.domain.breakdown import category_breakdown
from app.domain.flows import month_summary


def txn(day, amount, category="Food", kind="expense", **extra):
    return {"date": day, "amount_sen": amount, "type": kind, "category": category, **extra}


def budget(category, limit):
    return {"category": category, "limit_sen": limit, "updated_at": None}


# ------------------------------------------------------------------ category rules
@pytest.mark.parametrize("name", ["Refund", "transfer", "BNPL", "Salary", "allowance"])
def test_categories_that_change_the_maths_or_are_income_cannot_have_a_budget(name):
    with pytest.raises(ValueError):
        b.budget_category(name)


def test_a_built_in_name_is_spelled_the_apps_way_and_an_own_name_kept():
    assert b.budget_category("  food ") == "Food"
    assert b.budget_category("Drink/Dessert") == "Drink/Dessert"


# ------------------------------------------------------------------ status
TODAY = date(2026, 3, 15)


def test_states_at_the_exact_boundaries():
    rows = [txn("2026-02-03", 800, "Food"), txn("2026-02-04", 1000, "Transport")]
    rows.append(txn("2026-02-05", 799, "Shopping"))
    status = b.budget_status(
        [budget("Food", 1000), budget("Transport", 1000), budget("Shopping", 1000)],
        rows,
        "2026-02",
        TODAY,
    )
    states = {i.category: i.state for i in status.items}
    assert states == {"Food": "near", "Transport": "over", "Shopping": "ok"}
    food = next(i for i in status.items if i.category == "Food")
    assert (food.spent_sen, food.remaining_sen, food.percent) == (800, 200, 0.8)


def test_an_empty_ledger_gives_zero_spent_and_ok():
    status = b.budget_status([budget("Food", 5000)], [], "2026-03", TODAY)
    (item,) = status.items
    assert (item.spent_sen, item.state, item.percent) == (0, "ok", 0.0)
    assert status.total_spent_sen == 0
    assert status.unbudgeted_spend_sen == 0


def test_budget_names_match_categories_case_insensitively():
    rows = [txn("2026-03-02", 1500, "Drink/Dessert")]
    status = b.budget_status([budget("drink/dessert", 3000)], rows, "2026-03", TODAY)
    assert status.items[0].spent_sen == 1500


def test_refunds_and_transfers_follow_the_month_summary():
    rows = [
        txn("2026-02-02", 5000, "Shopping"),
        txn("2026-02-03", 2000, "Refund", kind="income"),
        txn("2026-02-04", 9000, "Transfer"),
        txn("2026-02-05", 3000, "Food"),
    ]
    status = b.budget_status([budget("Shopping", 10000)], rows, "2026-02", TODAY)
    summary = {m.month: m for m in month_summary(rows)}["2026-02"]
    # the category bar shows what was spent there (refunds are taken off the month total)
    assert status.items[0].spent_sen == 5000
    assert status.unbudgeted_spend_sen == 3000
    assert status.refund_sen == 2000
    assert status.month_spend_sen == summary.spend_sen == 6000
    assert status.total_spent_sen + status.unbudgeted_spend_sen - status.refund_sen == 6000


def test_bnpl_plan_payments_count_in_their_own_row_not_in_a_budget():
    rows = [txn("2026-02-10", 26600, "BNPL", is_bnpl=True), txn("2026-02-11", 1000, "Shopping")]
    status = b.budget_status([budget("Shopping", 5000)], rows, "2026-02", TODAY)
    assert status.items[0].spent_sen == 1000
    assert status.unbudgeted_spend_sen == 26600


def test_pace_is_projected_only_for_the_current_month():
    rows = [txn("2026-03-05", 1500, "Food")]
    current = b.budget_status([budget("Food", 3800)], rows, "2026-03", TODAY)
    item = current.items[0]
    assert current.is_current and current.days_elapsed == 15 and current.days_in_month == 31
    assert item.state == "ok"  # 1500 / 3800 so far
    assert item.projected_sen == 1500 * 31 // 15  # 3100
    assert item.projected_state == "near"  # 3100 / 3800 = 82% by the end of the month
    past = b.budget_status([budget("Food", 3800)], rows, "2026-02", TODAY)
    assert past.items[0].projected_sen is None and not past.is_current
    assert past.days_elapsed == past.days_in_month == 28


def test_status_totals_equal_the_spending_breakdown_on_persona_data():
    from pathlib import Path

    from app.domain.csv_import import parse_csv

    path = Path(__file__).resolve().parents[3] / "data" / "personas" / "frequent_bnpl.csv"
    preview = parse_csv(path.read_text(encoding="utf-8"))
    rows = [
        {"date": r.date, "amount_sen": r.amount_sen, "type": r.type, "category": r.category_guess}
        for r in preview.rows
    ]
    month = "2025-09"
    breakdown = category_breakdown(rows, month)
    names = [c.category for c in breakdown.categories][:3]
    status = b.budget_status([budget(n, 100_000) for n in names], rows, month, TODAY)
    assert status.total_spent_sen + status.unbudgeted_spend_sen == breakdown.gross_spend_sen
    assert status.month_spend_sen == breakdown.spend_sen


# ------------------------------------------------------------------ suggestion
def item(kind, name, amount, anchor, cadence="monthly"):
    return {
        "kind": kind,
        "name": name,
        "match_text": name,
        "amount_sen": amount,
        "cadence": cadence,
        "anchor_date": anchor,
        "active": True,
        "custom_interval_days": None,
    }


def plan_with(due, amount, paid=False):
    return {"installments": [{"due_date": due, "amount_sen": amount, "is_paid": paid, "seq": 1}]}


def test_the_suggestion_arithmetic_by_hand():
    items = [item("income", "Allowance from Ayah", 100_000, "2026-01-01"),
             item("bill", "Rent bilik", 30_000, "2026-01-03")]  # fmt: skip
    plans = [plan_with("2026-03-20", 10_000), plan_with("2026-03-21", 5_000, paid=True)]
    rows = []
    for month in ("2025-12", "2026-01", "2026-02"):
        rows += [
            txn(f"{month}-05", 30_000, "Rent", description="Rent bilik"),  # covered by the bill
            txn(f"{month}-06", 30_000, "Food"),
            txn(f"{month}-07", 10_000, "Transport"),
            txn(f"{month}-08", 8_000, "BNPL", is_bnpl=True),  # a plan payment: not discretionary
        ]
    s = b.suggest_budget(items, plans, rows, "2026-03", TODAY)
    assert (s.income_sen, s.income_basis) == (100_000, "recurring")
    assert (s.bills_sen, s.instalments_sen) == (30_000, 10_000)
    assert s.buffer_sen == 10_000  # 10% of income
    assert s.pool_sen == 50_000
    assert s.months_used == ["2025-12", "2026-01", "2026-02"]
    by = {i.category: i for i in s.items}
    assert set(by) == {"Food", "Transport"}
    assert (by["Food"].share, by["Transport"].share) == (0.75, 0.25)
    assert by["Food"].recent_monthly_sen == 30_000
    assert (by["Food"].limit_sen, by["Transport"].limit_sen) == (37_500, 12_500)
    assert sum(i.limit_sen for i in s.items) <= s.pool_sen


def test_limits_are_rounded_down_to_rm5():
    rows = [txn("2026-02-06", 2, "Food"), txn("2026-02-07", 1, "Transport")]
    items = [item("income", "Allowance", 10_000, "2026-01-01")]
    s = b.suggest_budget(items, [], rows, "2026-03", TODAY)
    assert s.pool_sen == 9_000
    assert all(i.limit_sen % 500 == 0 for i in s.items)
    assert {i.category: i.limit_sen for i in s.items} == {"Food": 6_000, "Transport": 3_000}


def test_without_recurring_income_the_average_of_earlier_months_is_used():
    rows = [
        txn("2026-01-10", 40_000, "Salary", kind="income"),
        txn("2026-02-10", 60_000, "Salary", kind="income"),
        txn("2026-02-12", 5_000, "Food"),
    ]
    s = b.suggest_budget([], [], rows, "2026-03", TODAY)
    assert (s.income_sen, s.income_basis) == (50_000, "average")
    assert s.months_used == ["2026-01", "2026-02"]


def test_no_history_and_no_income_says_so():
    s = b.suggest_budget([], [], [], "2026-03", TODAY)
    assert (s.income_sen, s.income_basis, s.pool_sen, s.items) == (0, "none", 0, [])
    assert any("no income" in n.lower() for n in s.notes)


def test_commitments_above_income_leave_an_empty_pool_and_a_note():
    items = [item("income", "Allowance", 50_000, "2026-01-01"),
             item("bill", "Rent", 60_000, "2026-01-02")]  # fmt: skip
    rows = [txn("2026-02-06", 10_000, "Food")]
    s = b.suggest_budget(items, [], rows, "2026-03", TODAY)
    assert s.pool_sen == 0
    assert s.items == []
    assert any("nothing is left" in n.lower() for n in s.notes)


def test_the_current_month_is_not_used_as_history():
    rows = [txn("2026-03-02", 50_000, "Shopping"), txn("2026-02-02", 1_000, "Food")]
    items = [item("income", "Allowance", 20_000, "2026-01-01")]
    s = b.suggest_budget(items, [], rows, "2026-03", TODAY)
    assert [i.category for i in s.items] == ["Food"]
