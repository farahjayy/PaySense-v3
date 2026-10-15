import pytest

from app.domain.breakdown import category_breakdown
from app.domain.flows import month_summary


def txn(day: str, amount_sen: int, type_: str = "expense", category: str = "Food") -> dict:
    return {"date": day, "amount_sen": amount_sen, "type": type_, "category": category}


JUNE = [
    txn("2026-06-02", 1000, category="Food"),
    txn("2026-06-03", 3000, category="Food"),
    txn("2026-06-04", 4000, category="Transport"),
    txn("2026-06-05", 2000, category="Bills"),
    txn("2026-06-06", 100000, "income", "Allowance"),
]


def test_spend_is_grouped_by_category_biggest_first():
    result = category_breakdown(JUNE, "2026-06")

    assert [(c.category, c.spend_sen, c.count) for c in result.categories] == [
        ("Food", 4000, 2),
        ("Transport", 4000, 1),
        ("Bills", 2000, 1),
    ]  # a tie is broken by name, so the order never flickers


def test_each_share_is_its_part_of_what_was_spent():
    result = category_breakdown(JUNE, "2026-06")

    assert result.gross_spend_sen == 10000
    assert [c.share for c in result.categories] == [0.4, 0.4, 0.2]


def test_income_is_reported_but_is_not_a_spending_category():
    result = category_breakdown(JUNE, "2026-06")

    assert result.income_sen == 100000
    assert "Allowance" not in [c.category for c in result.categories]


def test_only_the_asked_month_is_counted():
    rows = [*JUNE, txn("2026-05-31", 9999), txn("2026-07-01", 8888)]

    result = category_breakdown(rows, "2026-06")

    assert result.gross_spend_sen == 10000


def test_a_transfer_between_own_accounts_is_ignored_in_both_directions():
    rows = [
        *JUNE,
        txn("2026-06-07", 2000, "expense", "Transfer"),
        txn("2026-06-07", 2000, "income", "Transfer"),
        txn("2026-06-07", 2000, "savings", "Transfer"),
    ]

    assert category_breakdown(rows, "2026-06") == category_breakdown(JUNE, "2026-06")


def test_a_refund_is_taken_off_the_total_but_never_shown_as_a_category():
    rows = [*JUNE, txn("2026-06-08", 2500, "income", "Refund")]

    result = category_breakdown(rows, "2026-06")

    assert result.refund_sen == 2500
    assert result.gross_spend_sen == 10000
    assert result.spend_sen == 7500
    assert "Refund" not in [c.category for c in result.categories]


def test_a_refund_larger_than_the_spending_leaves_nothing_spent_not_less_than_nothing():
    rows = [txn("2026-06-02", 1000), txn("2026-06-03", 5000, "income", "Refund")]

    assert category_breakdown(rows, "2026-06").spend_sen == 0


def test_savings_are_reported_beside_spending_not_inside_it():
    rows = [*JUNE, txn("2026-06-09", 7000, "savings", "Saving")]

    result = category_breakdown(rows, "2026-06")

    assert result.savings_sen == 7000
    assert result.spend_sen == 10000
    assert "Saving" not in [c.category for c in result.categories]


def test_a_bnpl_instalment_is_its_own_row():
    rows = [*JUNE, txn("2026-06-10", 5000, category="BNPL")]

    result = category_breakdown(rows, "2026-06")

    assert ("BNPL", 5000, 1) in [(c.category, c.spend_sen, c.count) for c in result.categories]


def test_a_month_with_nothing_in_it_is_all_zeros_and_has_no_categories():
    result = category_breakdown(JUNE, "2026-01")

    assert (result.income_sen, result.spend_sen, result.gross_spend_sen) == (0, 0, 0)
    assert result.categories == ()


@pytest.mark.parametrize("month", ["2026-06", "2026-05", "2026-07"])
def test_the_total_spent_is_the_month_summarys_total_spent(month):
    # One definition of "spent": the dashboard and this panel can never disagree.
    rows = [
        *JUNE,
        txn("2026-05-20", 1234),
        txn("2026-07-02", 4321, category="Shopping"),
        txn("2026-06-08", 2500, "income", "Refund"),
        txn("2026-06-09", 700, "expense", "Transfer"),
    ]
    summary = {m.month: m for m in month_summary(rows)}

    result = category_breakdown(rows, month)

    assert result.spend_sen == summary[month].spend_sen
    assert result.income_sen == summary[month].income_sen
    assert result.savings_sen == summary[month].savings_sen
