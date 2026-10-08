from datetime import date

import pytest

from app.domain.flows import classify, history_span, month_summary


def txn(day: str, amount_sen: int, type_: str = "expense", category: str = "Food") -> dict:
    return {"date": day, "amount_sen": amount_sen, "type": type_, "category": category}


@pytest.mark.parametrize(
    ("type_", "category", "flow"),
    [
        ("income", "Salary", "income"),
        ("income", "Allowance", "income"),
        ("expense", "Food", "spend"),
        ("expense", "BNPL", "spend"),
        ("savings", "Savings", "savings"),
        ("income", "Refund", "refund"),
        ("expense", "Refund", "refund"),
        ("expense", "Transfer", "transfer"),
        ("income", "Transfer", "transfer"),
        ("savings", "Transfer", "transfer"),
    ],
)
def test_classify(type_, category, flow):
    assert classify(txn("2026-01-05", 100, type_, category)) == flow


def test_empty_history_has_an_empty_summary_and_no_span():
    assert month_summary([]) == []
    assert history_span([], date(2026, 1, 1)) is None


def test_month_summary_groups_by_calendar_month_in_ascending_order():
    rows = [
        txn("2026-02-03", 5000, "income", "Allowance"),
        txn("2026-01-31", 1200),
        txn("2026-01-05", 80000, "income", "Salary"),
        txn("2026-02-10", 3000),
    ]

    summary = month_summary(rows)

    assert [m.month for m in summary] == ["2026-01", "2026-02"]
    jan, feb = summary
    assert (jan.income_sen, jan.spend_sen, jan.net_sen) == (80000, 1200, 78800)
    assert (feb.income_sen, feb.spend_sen, feb.net_sen) == (5000, 3000, 2000)


def test_a_refund_reduces_that_months_spend_and_never_counts_as_income():
    rows = [
        txn("2026-03-02", 10000),
        txn("2026-03-09", 4000, "income", "Refund"),
    ]

    (march,) = month_summary(rows)

    assert march.income_sen == 0
    assert march.spend_sen == 6000
    assert march.refund_sen == 4000
    assert march.net_sen == -6000


def test_a_refund_larger_than_the_months_spend_cannot_make_spend_negative():
    rows = [txn("2026-03-02", 1000), txn("2026-03-09", 5000, "income", "Refund")]

    (march,) = month_summary(rows)

    assert march.spend_sen == 0
    assert march.net_sen == 0


def test_transfers_change_nothing_in_either_direction():
    rows = [
        txn("2026-03-02", 20000, "expense", "Transfer"),
        txn("2026-03-02", 20000, "income", "Transfer"),
        txn("2026-03-05", 1500),
    ]

    (march,) = month_summary(rows)

    assert (march.income_sen, march.spend_sen, march.net_sen) == (0, 1500, -1500)


def test_savings_are_reported_but_not_counted_as_spend():
    rows = [txn("2026-03-02", 30000, "income", "Salary"), txn("2026-03-03", 5000, "savings", "ASB")]

    (march,) = month_summary(rows)

    assert march.savings_sen == 5000
    assert march.spend_sen == 0
    assert march.net_sen == 30000


def test_a_month_with_only_transfers_still_appears_with_zeros():
    (march,) = month_summary([txn("2026-03-02", 100, "expense", "Transfer")])

    assert march.month == "2026-03"
    assert (march.income_sen, march.spend_sen) == (0, 0)


def test_dates_may_be_iso_strings_or_date_objects():
    rows = [txn("2026-03-02", 100), {**txn("2026-03-03", 200), "date": date(2026, 3, 3)}]

    (march,) = month_summary(rows)

    assert march.spend_sen == 300


def test_history_span_counts_calendar_months_that_have_data():
    rows = [txn("2026-01-05", 1), txn("2026-01-20", 1), txn("2026-03-02", 1), txn("2026-05-30", 1)]

    span = history_span(rows, today=date(2026, 6, 10))

    assert span is not None
    assert span.first_date == date(2026, 1, 5)
    assert span.last_date == date(2026, 5, 30)
    assert span.distinct_months == 3  # Jan, Mar, May — a gap month does not count
    assert span.span_days == 146
    assert span.days_since_last == 11


def test_history_span_ignores_transfers():
    rows = [txn("2025-12-01", 1, "expense", "Transfer"), txn("2026-02-01", 1)]

    span = history_span(rows, today=date(2026, 2, 2))

    assert span is not None
    assert span.first_date == date(2026, 2, 1)
    assert span.distinct_months == 1


def test_history_of_only_transfers_has_no_span():
    assert history_span([txn("2026-02-01", 1, "expense", "Transfer")], date(2026, 2, 2)) is None
