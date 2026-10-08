from datetime import date

import numpy as np
import pytest

from app.engines.forecasting.series import MONDAY_FIRST_GAP_MESSAGE, build_weekly_series


def row(day, amount, kind="expense", category="Food", description="x", **extra):
    return {
        "date": day,
        "amount_sen": amount,
        "type": kind,
        "category": category,
        "description": description,
        **extra,
    }


# 2025-01-06 is a Monday.
TODAY = date(2025, 2, 3)
LOGGED_THROUGH_SUNDAY = row(
    date(2025, 2, 2), 1, category="Transfer"
)  #   # a Monday: the weeks of 6 Jan .. 26 Jan are complete, 27 Jan too


def test_weeks_run_monday_to_sunday_and_the_current_week_is_excluded():
    rows = [
        row(date(2025, 1, 6), 100),
        row(date(2025, 1, 12), 50),  # the Sunday of week 1
        row(date(2025, 1, 13), 70),  # week 2
        row(date(2025, 2, 3), 999),  # today: the current week must not appear
    ]

    series = build_weekly_series([*rows, LOGGED_THROUGH_SUNDAY], TODAY)

    assert series.start == date(2025, 1, 6)
    assert list(series.spend[:2]) == [150, 70]
    assert series.weeks == 4  # 6 Jan, 13 Jan, 20 Jan, 27 Jan; the week of 3 Feb is incomplete
    assert series.spend.sum() == 220


def test_quiet_weeks_are_explicit_zeros_not_missing():
    series = build_weekly_series(
        [row(date(2025, 1, 6), 100), row(date(2025, 1, 27), 40), LOGGED_THROUGH_SUNDAY], TODAY
    )

    assert list(series.spend) == [100, 0, 0, 40]


def test_a_refund_nets_against_that_weeks_spend_and_never_makes_it_negative():
    rows = [
        row(date(2025, 1, 6), 100),
        row(date(2025, 1, 7), 30, kind="income", category="Refund"),
        row(date(2025, 1, 14), 10),
        row(date(2025, 1, 15), 500, kind="income", category="Refund"),
    ]

    series = build_weekly_series([*rows, LOGGED_THROUGH_SUNDAY], TODAY)

    assert list(series.spend[:2]) == [70, 0]
    assert series.income.sum() == 0  # a refund is not income


def test_transfers_savings_and_plan_payments_are_not_discretionary_spend():
    rows = [
        row(date(2025, 1, 6), 100, category="Transfer"),
        row(date(2025, 1, 7), 200, kind="savings", category="Savings"),
        row(date(2025, 1, 8), 300, category="BNPL", bnpl_plan_id="p1"),
        row(date(2025, 1, 9), 400, category="BNPL", is_bnpl=True),
        row(date(2025, 1, 6), 50),
    ]

    series = build_weekly_series([*rows, LOGGED_THROUGH_SUNDAY], TODAY)

    assert series.spend.sum() == 50


def test_confirmed_recurring_items_are_taken_out_of_the_variable_series():
    rows = [
        row(
            date(2025, 1, 6),
            45000,
            category="Bills",
            description="Sewa bilik 01",
            recurring_item_id="r1",
        ),
        row(date(2025, 1, 7), 5000, category="Bills", description="Netflix subscription"),
        row(date(2025, 1, 6), 20, description="Nasi lemak"),
        row(
            date(2025, 1, 9),
            30000,
            kind="income",
            category="Allowance",
            description="Duit belanja",
            recurring_item_id="r2",
        ),
        row(date(2025, 1, 10), 8000, kind="income", category="Gig", description="Grab payout"),
    ]

    series = build_weekly_series(
        [*rows, LOGGED_THROUGH_SUNDAY], TODAY, covered=[("expense", "Netflix Subscription")]
    )

    assert series.spend.sum() == 20  # rent linked, Netflix confirmed by name
    assert series.income.sum() == 8000  # the allowance is a known flow, the gig is not


def test_income_is_summed_per_week():
    rows = [
        row(date(2025, 1, 6), 8000, kind="income", category="Gig"),
        row(date(2025, 1, 10), 2000, kind="income", category="Gig"),
        row(date(2025, 1, 16), 5000, kind="income", category="Gig"),
    ]

    series = build_weekly_series([*rows, LOGGED_THROUGH_SUNDAY], TODAY)

    assert list(series.income[:2]) == [10000, 5000]


def test_history_that_never_completes_a_week_gives_an_empty_series():
    series = build_weekly_series([row(date(2025, 2, 4), 100)], date(2025, 2, 6))

    assert series.weeks == 0 and len(series.spend) == 0 and len(series.income) == 0


def test_an_empty_ledger_gives_an_empty_series():
    series = build_weekly_series([], TODAY)

    assert series.weeks == 0


def test_weeks_are_dated_from_the_first_complete_week():
    series = build_weekly_series(
        [row(date(2025, 1, 8), 100), LOGGED_THROUGH_SUNDAY], TODAY
    )  # a Wednesday

    assert series.start == date(2025, 1, 13)  # the first Monday that begins a complete week
    assert series.spend.sum() == 0  # the Wednesday belongs to a partial first week
    assert MONDAY_FIRST_GAP_MESSAGE


def test_the_input_rows_are_not_modified():
    rows = [row(date(2025, 1, 6), 100)]
    before = [dict(r) for r in rows]

    build_weekly_series([*rows, LOGGED_THROUGH_SUNDAY], TODAY)

    assert rows == before


def test_money_stays_integer_sen():
    series = build_weekly_series([row(date(2025, 1, 6), 12345), LOGGED_THROUGH_SUNDAY], TODAY)

    assert series.spend.dtype == np.int64
    assert pytest.approx(series.spend[0]) == 12345


def test_a_confirmed_item_with_no_letters_in_its_name_swallows_nothing():
    rows = [
        row(date(2025, 1, 6), 100, description=None),
        row(date(2025, 1, 13), 200, description=None),
    ]

    series = build_weekly_series(
        [*rows, LOGGED_THROUGH_SUNDAY], TODAY, covered=[("expense", "123"), ("expense", "7-11")]
    )

    assert series.spend.sum() == 300


def test_the_series_stops_at_the_last_logged_day_instead_of_counting_silent_weeks_as_zero():
    rows = [row(date(2025, 1, 6), 100), row(date(2025, 1, 13), 200)]  # nothing after 13 January

    series = build_weekly_series(rows, TODAY)

    assert series.weeks == 1 and list(series.spend) == [100]  # only the week that was fully logged
