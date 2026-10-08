"""The author's own scenarios, run through the real served LSTM (P4 acceptance, PRD section 6):

A RM600 purchase split over three months is Safe on RM2,000 monthly income, At Risk on RM500
monthly income, and At Risk with savings only and no income.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pytest

from app.engines.forecasting.service import build_forecast
from app.engines.forecasting.serving import served_forecaster

TODAY = date(2025, 5, 12)  # a Monday


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


RM600_OVER_THREE_MONTHS = Proposal(
    purchase_date=TODAY,
    cash_at_purchase_sen=0,
    instalments=tuple(Instalment(i + 1, date(2025, 6 + i, 12), 20000) for i in range(3)),
)


def ledger(income_sen, seed=0):
    rng = np.random.default_rng(seed)
    rows, day = [], date(2024, 12, 2)
    while day < TODAY:
        spend = int(max(rng.normal(6000, 1500), 500))  # about RM60 a week of food and transport
        rows.append(_row(day, spend, "expense", "Food", "Kedai makan"))
        day += timedelta(days=7)
    if income_sen:
        for m in range(12, 18):
            year, month = 2024 + (m - 1) // 12, (m - 1) % 12 + 1
            rows.append(
                _row(date(year, month, 1), income_sen, "income", "Allowance", "Duit belanja")
            )
    return rows


def _row(day, amount, kind, category, description):
    return {"date": day, "amount_sen": amount, "type": kind, "category": category,
            "description": description}  # fmt: skip


def items(income_sen):
    rent = {"kind": "bill", "name": "Sewa", "match_text": "sewa", "amount_sen": 30000,
            "cadence": "monthly", "custom_interval_days": None, "anchor_date": date(2025, 5, 1),
            "active": True}  # fmt: skip
    allowance = {**rent, "kind": "income", "name": "Allowance", "match_text": "duit belanja",
                 "amount_sen": income_sen}  # fmt: skip
    return [allowance, rent] if income_sen else [rent]


def forecast(income_sen, with_plan=True):
    return build_forecast(
        ledger(income_sen), items(income_sen), [], TODAY, served_forecaster(),
        proposed=RM600_OVER_THREE_MONTHS if with_plan else None, seed=7,
    )  # fmt: skip


def test_rm600_over_three_months_is_safe_on_rm2000_a_month():
    result = forecast(200000)

    assert result.status == "ok" and result.band == "Safe", result.simulation.p_shortfall


def test_the_same_purchase_is_at_risk_on_rm500_a_month():
    result = forecast(50000)

    assert result.band == "At Risk", result.simulation.p_shortfall


def test_with_savings_only_and_no_income_the_purchase_is_at_risk():
    result = forecast(0)

    assert result.status == "ok" and result.band == "At Risk", result.simulation.p_shortfall


@pytest.mark.parametrize("income", [200000, 50000])
def test_adding_the_purchase_never_makes_a_user_safer(income):
    without, with_plan = forecast(income, with_plan=False), forecast(income)

    assert with_plan.simulation.p_shortfall >= without.simulation.p_shortfall
