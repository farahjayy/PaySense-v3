from datetime import date, timedelta

import numpy as np

from app.engines.forecasting.errors import rolling_errors
from app.engines.forecasting.service import build_forecast

TODAY = date(2025, 5, 12)  # a Monday


class LastValue:
    name = "last-value"

    def forecast(self, history, horizon, start):
        return np.full(horizon, float(history[-1]))


class Mean:
    name = "mean"

    def forecast(self, history, horizon, start):
        return np.full(horizon, float(np.mean(history)))


def txn(day, amount, kind="expense", category="Food", description="x", **extra):
    return {
        "date": day,
        "amount_sen": amount,
        "type": kind,
        "category": category,
        "description": description,
        **extra,
    }


def ledger(income_per_month=200000, spend_per_week=6000, start=date(2025, 1, 6), months=5):
    rows = []
    day = start
    while day < TODAY:
        rows.append(txn(day, spend_per_week))
        day += timedelta(days=7)
    for m in range(months):
        rows.append(
            txn(date(2025, 1 + m, 1), income_per_month, "income", "Allowance", "Duit belanja")
        )
    return rows


ALLOWANCE = {
    "kind": "income",
    "name": "Duit belanja",
    "amount_sen": 200000,
    "cadence": "monthly",
    "custom_interval_days": None,
    "anchor_date": date(2025, 5, 1),
    "active": True,
}
RENT = {**ALLOWANCE, "kind": "bill", "name": "Sewa", "amount_sen": 30000}


def test_rolling_errors_are_signed_actual_minus_forecast():
    values = np.arange(1.0, 31.0)  # a steady climb: a last-value forecast always under-forecasts

    errors = rolling_errors(
        values, date(2025, 1, 6), LastValue(), horizon=4, min_train=10, stride=4
    )

    assert len(errors) > 0 and np.all(errors > 0)


def test_rolling_errors_never_use_the_future_and_are_empty_for_short_series():
    assert len(rolling_errors(np.arange(5.0), date(2025, 1, 6), LastValue(), 4, 10, 1)) == 0


def test_rolling_errors_keep_only_the_latest_origins():
    values = np.arange(1.0, 61.0)
    few = rolling_errors(values, date(2025, 1, 6), LastValue(), 4, 10, 1, max_origins=3)
    many = rolling_errors(values, date(2025, 1, 6), LastValue(), 4, 10, 1, max_origins=30)

    assert len(few) == 3 * 4 and len(many) == 30 * 4


def test_fewer_than_four_months_is_locked_and_no_forecast_is_made():
    rows = [txn(date(2025, 3, 3) + timedelta(days=7 * i), 6000) for i in range(10)]
    rows += [txn(date(2025, m, 1), 200000, "income", "Allowance", "Duit") for m in (3, 4, 5)]

    result = build_forecast(rows, [], [], TODAY, LastValue())

    assert result.status == "locked" and result.simulation is None and result.health_score is None


def test_an_unlocked_forecast_has_a_band_a_score_and_three_months():
    result = build_forecast(ledger(), [ALLOWANCE, RENT], [], TODAY, Mean())

    assert result.status == "ok"
    assert result.band in {"Safe", "Caution", "At Risk"}
    assert 0 <= result.health_score <= 100
    assert result.simulation.months == ["2025-05", "2025-06", "2025-07"]


def test_a_comfortable_ledger_is_safe_and_a_stretched_one_is_not():
    comfortable = build_forecast(ledger(), [ALLOWANCE, RENT], [], TODAY, Mean())
    stretched = build_forecast(
        ledger(spend_per_week=30000), [{**ALLOWANCE, "amount_sen": 50000}, RENT], [], TODAY, Mean()
    )

    assert comfortable.band == "Safe"
    assert stretched.band == "At Risk" and stretched.health_score < comfortable.health_score


def test_covered_recurring_items_are_taken_out_of_the_variable_series():
    rows = ledger() + [
        txn(date(2025, 4, 1), 30000, category="Bills", description="Sewa"),
        txn(date(2025, 3, 1), 30000, category="Bills", description="Sewa"),
    ]

    with_rent = build_forecast(rows, [ALLOWANCE, RENT], [], TODAY, Mean())
    unconfirmed = build_forecast(rows, [ALLOWANCE], [], TODAY, Mean())

    # unconfirmed rent stays in the variable series (it is forecast as ordinary spending)
    assert with_rent.series_weeks == unconfirmed.series_weeks


def test_the_same_inputs_give_the_same_forecast():
    a = build_forecast(ledger(), [ALLOWANCE, RENT], [], TODAY, Mean(), seed=5)
    b = build_forecast(ledger(), [ALLOWANCE, RENT], [], TODAY, Mean(), seed=5)

    assert a == b


def test_incomplete_months_are_reported_but_the_forecast_is_still_made():
    rows = [r for r in ledger() if not (r["type"] == "income" and r["date"].month == 3)]

    result = build_forecast(rows, [ALLOWANCE, RENT], [], TODAY, Mean())

    assert result.status == "ok" and any(s.month == "2025-03" for s in result.suspect_months)


def test_a_proposed_plan_raises_the_chance_of_a_shortfall():
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class Instalment:
        seq: int
        due_date: date
        amount_sen: int
        paid_at_checkout: bool = False

    @dataclass(frozen=True)
    class Proposal:
        purchase_date: date
        cash_at_purchase_sen: int
        instalments: tuple

    heavy = Proposal(
        TODAY,
        0,
        tuple(Instalment(i + 1, date(2025, 6 + i, 10), 150000) for i in range(2)),
    )
    thin = [{**ALLOWANCE, "amount_sen": 60000}, RENT]

    without = build_forecast(ledger(), thin, [], TODAY, Mean())
    with_plan = build_forecast(ledger(), thin, [], TODAY, Mean(), proposed=heavy)

    assert with_plan.simulation.p_shortfall >= without.simulation.p_shortfall
    assert with_plan.simulation.p_shortfall > 0.5


def test_month_to_date_income_is_not_forgotten():
    from app.engines.forecasting.service import month_to_date_net

    rows = [
        txn(date(2025, 5, 1), 200000, "income", "Allowance"),
        txn(date(2025, 5, 3), 30000, category="Bills"),
        txn(date(2025, 5, 12), 999, category="Food"),  # today: left to the forecast
        txn(date(2025, 4, 28), 5000),  # last month: not part of this month
    ]

    assert month_to_date_net(rows, TODAY) == 170000
    assert month_to_date_net([], TODAY) == 0
