from datetime import date

from app.engines.forecasting.completeness import (
    LOW_SPEND_FRACTION,
    MIN_MONTHS,
    assess,
)


def txn(day, amount, kind="expense", category="Food"):
    return {
        "date": day,
        "amount_sen": amount,
        "type": kind,
        "category": category,
        "description": "x",
    }


def month_rows(year, month, spend=30000, income=100000, spends=6, with_income=True):
    rows = [txn(date(year, month, 3 + i), spend // spends) for i in range(spends)]
    if with_income:
        rows.append(txn(date(year, month, 1), income, "income", "Allowance"))
    return rows


def ledger(months, overrides=None):
    rows = []
    for year, month in months:
        rows += month_rows(year, month, **(overrides or {}).get((year, month), {}))
    return rows


FOUR_MONTHS = [(2025, 1), (2025, 2), (2025, 3), (2025, 4)]
TODAY = date(2025, 5, 12)  # May is the current, partial month


def test_fewer_than_four_months_locks_the_forecast():
    result = assess(ledger(FOUR_MONTHS[:3]), date(2025, 4, 20))

    assert result.status == "locked" and result.months_of_history == 3 < MIN_MONTHS


def test_four_months_of_history_unlock_it():
    result = assess(ledger(FOUR_MONTHS), TODAY)

    assert result.status == "ok" and result.months_of_history == 4


def test_an_empty_ledger_is_locked_with_no_history():
    result = assess([], TODAY)

    assert (
        result.status == "locked" and result.months_of_history == 0 and result.suspect_months == []
    )


def test_a_clean_ledger_has_no_warnings():
    assert assess(ledger(FOUR_MONTHS), TODAY).suspect_months == []


def test_a_month_without_income_is_flagged_when_other_months_have_it():
    rows = ledger(FOUR_MONTHS, {(2025, 3): {"with_income": False}})

    (suspect,) = assess(rows, TODAY).suspect_months

    assert suspect.month == "2025-03" and suspect.reason == "no_income"


def test_a_user_who_never_logs_income_is_not_flagged_for_it():
    rows = ledger(FOUR_MONTHS, {ym: {"with_income": False} for ym in FOUR_MONTHS})

    assert assess(rows, TODAY).suspect_months == []


def test_a_month_with_far_less_spending_than_usual_is_flagged():
    rows = ledger(FOUR_MONTHS, {(2025, 2): {"spend": 3000, "spends": 1}})

    (suspect,) = assess(rows, TODAY).suspect_months

    assert suspect.month == "2025-02" and suspect.reason == "low_spend"


def test_a_modest_dip_is_not_flagged():
    just_above = int(30000 * (LOW_SPEND_FRACTION + 0.1))
    rows = ledger(FOUR_MONTHS, {(2025, 2): {"spend": just_above, "spends": 6}})

    assert assess(rows, TODAY).suspect_months == []


def test_the_current_partial_month_is_never_flagged():
    rows = ledger(FOUR_MONTHS) + [txn(date(2025, 5, 2), 500)]  # a quiet start to May

    assert assess(rows, TODAY).suspect_months == []


def test_transfers_do_not_count_as_history_or_as_spending():
    rows = ledger(FOUR_MONTHS[:3]) + [txn(date(2025, 4, 2), 50000, category="Transfer")]

    result = assess(rows, date(2025, 4, 20))

    assert result.months_of_history == 3 and result.status == "locked"


def test_suspect_months_are_listed_in_date_order_with_a_readable_detail():
    rows = ledger(
        FOUR_MONTHS + [(2025, 5)],
        {(2025, 4): {"with_income": False}, (2025, 2): {"spend": 3000, "spends": 1}},
    )

    suspects = assess(rows, date(2025, 6, 10)).suspect_months

    assert [s.month for s in suspects] == ["2025-02", "2025-04"]
    assert all(s.detail for s in suspects)


def test_rows_dated_after_today_do_not_count_toward_the_four_month_gate():
    rows = ledger(FOUR_MONTHS[:1]) + [txn(date(2025, m, 2), 500) for m in (6, 7, 8)]

    result = assess(rows, TODAY)

    assert result.months_of_history == 1 and result.status == "locked"
