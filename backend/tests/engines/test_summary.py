from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pytest

from app.engines.forecasting.models import MovingAverage
from app.engines.forecasting.summary import (
    build_feature_inputs,
    expected_monthly_income,
    monthly_equivalent_sen,
)
from app.engines.risk.features import compute_features

TODAY = date(2025, 5, 12)  # a Monday


def txn(day, amount, kind="expense", category="Food", description="Kedai makan"):
    return {
        "date": day,
        "amount_sen": amount,
        "type": kind,
        "category": category,
        "description": description,
    }


def ledger(income=200000):
    rows, day = [], date(2024, 12, 2)
    rng = np.random.default_rng(1)
    while day < TODAY:
        rows.append(txn(day, int(rng.normal(6000, 800))))
        day += timedelta(days=7)
    rows += [
        txn(date(2024 + (m - 1) // 12, (m - 1) % 12 + 1, 1), income, "income", "Allowance", "Duit")
        for m in range(12, 18)
    ]
    return rows


ITEMS = [
    {"kind": "income", "name": "Duit", "match_text": "duit", "amount_sen": 200000,
     "cadence": "monthly", "custom_interval_days": None, "anchor_date": date(2025, 5, 1),
     "active": True},
    {"kind": "bill", "name": "Sewa", "match_text": "sewa", "amount_sen": 30000,
     "cadence": "monthly", "custom_interval_days": None, "anchor_date": date(2025, 5, 1),
     "active": True},
]  # fmt: skip


@dataclass(frozen=True)
class Instalment:
    seq: int
    due_date: date
    amount_sen: int
    paid_at_checkout: bool = False


@dataclass(frozen=True)
class Proposal:
    provider: str
    purchase_date: date
    instalments: tuple
    upfront_sen: int = 0
    monthly_fee_rate_pct: float = 0.0

    @property
    def cash_at_purchase_sen(self):
        return self.upfront_sen + sum(i.amount_sen for i in self.instalments if i.paid_at_checkout)

    @property
    def total_payable_sen(self):
        return sum(i.amount_sen for i in self.instalments)


PROPOSAL = Proposal(
    "spaylater", TODAY, tuple(Instalment(i + 1, date(2025, 6 + i, 12), 20000) for i in range(3))
)
EXISTING = [
    {
        "provider": "spaylater",
        "installments": [
            {"seq": 1, "due_date": date(2025, 4, 20), "amount_sen": 10000, "is_paid": True},
            {"seq": 2, "due_date": date(2025, 5, 20), "amount_sen": 10000, "is_paid": False},
            {"seq": 3, "due_date": date(2025, 6, 20), "amount_sen": 10000, "is_paid": False},
        ],
    },
    {
        "provider": "atome",
        "installments": [
            {"seq": 1, "due_date": date(2025, 5, 25), "amount_sen": 5000, "is_paid": False}
        ],
    },
]


def build(**overrides):
    args = dict(
        rows=ledger(), items=ITEMS, plans=EXISTING, proposal=PROPOSAL,
        provider_limits={"spaylater": 300000}, today=TODAY, forecaster=MovingAverage(8), seed=3,
        paths=300,
    )  # fmt: skip
    args.update(overrides)
    return build_feature_inputs(**args)


def test_the_expected_monthly_income_is_the_recent_complete_months_average():
    rows = [
        txn(date(2025, 2, 1), 100000, "income"),
        txn(date(2025, 3, 1), 200000, "income"),
        txn(date(2025, 4, 1), 300000, "income"),
        txn(date(2025, 5, 1), 999999, "income"),
    ]

    assert expected_monthly_income(rows, TODAY) == 200000  # Feb-Apr; May is still in progress


def test_refunds_and_transfers_are_not_income_for_the_expected_figure():
    rows = [
        txn(date(2025, 4, 1), 100000, "income"),
        txn(date(2025, 4, 2), 50000, "income", "Refund"),
        txn(date(2025, 4, 3), 70000, "income", "Transfer"),
    ]

    assert expected_monthly_income(rows, TODAY) == 100000


def test_no_complete_month_means_no_expected_income():
    assert expected_monthly_income([txn(date(2025, 5, 2), 100000, "income")], TODAY) == 0


def test_bills_are_converted_to_a_monthly_equivalent_by_cadence():
    def bill(cadence, amount=12000, interval=None):
        return {"amount_sen": amount, "cadence": cadence, "custom_interval_days": interval}

    assert monthly_equivalent_sen(bill("monthly")) == 12000
    assert monthly_equivalent_sen(bill("weekly")) == pytest.approx(12000 * 52 / 12)
    assert monthly_equivalent_sen(bill("biweekly")) == pytest.approx(12000 * 26 / 12)
    assert monthly_equivalent_sen(bill("semester")) == pytest.approx(12000 * 2 / 12)
    custom = monthly_equivalent_sen(bill("custom", interval=30))
    assert custom == pytest.approx(12000 * 365 / 30 / 12)


def test_a_locked_ledger_gives_no_feature_inputs():
    assert build(rows=[txn(date(2025, 5, 2), 100)]) is None


def test_commitments_come_from_existing_plans_bills_and_the_recorded_limit():
    built = build()

    c = built.inputs.commitments
    assert c.active_plans == 2
    assert c.outstanding_bnpl_sen == 25000  # 10000 + 10000 + 5000 unpaid
    assert c.provider_outstanding_sen == 20000
    assert c.provider_limit_sen == 300000
    assert c.monthly_debt_like_bills_sen == 30000
    assert c.monthly_bnpl_sen == 8333  # RM250 of unpaid obligations spread over 3 months


def test_no_recorded_limit_is_passed_through_as_none():
    assert build(provider_limits={}).inputs.commitments.provider_limit_sen is None


def test_the_plan_input_describes_the_proposed_plan():
    plan = build().inputs.plan

    assert plan.instalment_amounts_sen == (20000, 20000, 20000)
    assert plan.financed_payable_sen == 60000 and plan.upfront_sen == 0


def test_the_engine_one_summary_comes_from_the_simulation_without_the_purchase():
    built = build()

    e1 = built.inputs.engine1
    assert 3000 < e1.disc_weekly_p50_sen < 9000 and e1.disc_weekly_p90_sen >= e1.disc_weekly_p50_sen
    assert e1.disc_volatility_sen > 0
    assert e1.margin_monthly_p50_without_sen > 0
    assert e1.income_p10_monthly_sen > 0
    assert built.inputs.expected_monthly_income_sen == 200000


def test_the_label_is_the_simulated_chance_of_a_shortfall_with_the_purchase():
    built = build()

    assert built.p_with == built.with_plan.simulation.p_shortfall
    assert built.p_without == built.without.simulation.p_shortfall
    assert built.p_with >= built.p_without  # the same random draws: a purchase cannot help


def test_a_heavy_purchase_on_a_thin_income_has_a_higher_label_than_a_light_one():
    thin = [{**ITEMS[0], "amount_sen": 40000}, ITEMS[1]]
    heavy = Proposal(
        "spaylater", TODAY, tuple(Instalment(i + 1, date(2025, 6 + i, 12), 90000) for i in range(3))
    )
    light = Proposal("spaylater", TODAY, (Instalment(1, date(2025, 6, 12), 3000),))

    assert build(items=thin, proposal=heavy).p_with > build(items=thin, proposal=light).p_with


def test_the_features_compute_from_the_inputs():
    values = compute_features(build().inputs)

    assert len(values) == 16 and all(np.isfinite(v) for v in values.values())
    assert values["num_instalments"] == 3 and values["instalment_amount"] == 200.0


def test_the_same_inputs_give_the_same_label():
    assert build().p_with == build().p_with


def _monthly_plan(count, first=date(2025, 6, 12), amount=5000):
    def due(i):
        month = first.month - 1 + i
        return date(first.year + month // 12, month % 12 + 1, first.day)

    return Proposal(
        "spaylater", TODAY, tuple(Instalment(i + 1, due(i), amount) for i in range(count))
    )


def test_a_24_instalment_plan_is_simulated_to_its_last_instalment():
    plan = _monthly_plan(24)  # last instalment on 12 May 2027, 105 weeks out

    built = build(proposal=plan, paths=100)

    last = max(i.due_date for i in plan.instalments).strftime("%Y-%m")
    for arm in (built.without, built.with_plan):  # the same horizon, so the arms are comparable
        assert not arm.simulation.horizon_capped
        assert arm.simulation.months[-1] == last
        assert arm.simulation.weeks > 52


def test_a_36_instalment_plan_also_fits_inside_the_risk_check_horizon():
    built = build(proposal=_monthly_plan(36), paths=100)

    assert not built.with_plan.simulation.horizon_capped
    assert built.with_plan.simulation.months[-1] == "2028-05"


def test_the_dashboard_forecast_keeps_its_own_cap_and_three_month_horizon():
    from app.engines.forecasting.service import build_forecast

    dashboard = build_forecast(ledger(), ITEMS, [], TODAY, MovingAverage(8), paths=100)

    assert len(dashboard.simulation.months) == 3
    assert not dashboard.simulation.horizon_capped and dashboard.simulation.weeks < 52
    long_end = date(2027, 5, 31)
    capped = build_forecast(ledger(), ITEMS, [], TODAY, MovingAverage(8), end=long_end, paths=100)
    assert capped.simulation.horizon_capped and capped.simulation.weeks == 52


def test_both_arms_also_report_the_per_month_definition_for_the_sensitivity_check():
    built = build(paths=100)

    assert 0 <= built.p_without_monthly <= 1 and 0 <= built.p_with_monthly <= 1
    assert built.p_with_monthly == built.with_plan.simulation.p_shortfall_monthly


def test_a_shared_cache_computes_the_without_purchase_simulation_once_per_plan_end(monkeypatch):
    import app.engines.forecasting.summary as summary_module

    real = summary_module.forecast_prepared
    calls = []

    def spy(*args, **kwargs):
        calls.append(kwargs.get("proposed") is not None)
        return real(*args, **kwargs)

    monkeypatch.setattr(summary_module, "forecast_prepared", spy)
    cache: dict = {}
    first = build(cache=cache)
    second = build(cache=cache)

    assert calls == [False, True, True]  # without once, with-plan twice
    assert first.p_without == second.p_without and first.p_with == second.p_with


def test_a_different_plan_end_does_not_reuse_the_cached_simulation(monkeypatch):
    import app.engines.forecasting.summary as summary_module

    real = summary_module.forecast_prepared
    without_calls = []

    def spy(*args, **kwargs):
        if kwargs.get("proposed") is None:
            without_calls.append(kwargs["end"])
        return real(*args, **kwargs)

    monkeypatch.setattr(summary_module, "forecast_prepared", spy)
    cache: dict = {}
    longer = Proposal(
        "spaylater", TODAY, tuple(Instalment(i + 1, date(2025, 6 + i, 12), 10000) for i in range(6))
    )
    build(cache=cache)
    build(cache=cache, proposal=longer)

    assert len(set(without_calls)) == 2


def test_the_cache_does_not_change_any_number():
    plain = build()
    cached = build(cache={})
    assert (cached.p_with, cached.p_without) == (plain.p_with, plain.p_without)
    assert compute_features(cached.inputs) == compute_features(plain.inputs)


def test_the_ledger_is_read_once_however_many_candidate_plans_are_tried(monkeypatch):
    import app.engines.forecasting.summary as summary_module

    real = summary_module.prepare_ledger
    calls = []

    def spy(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(summary_module, "prepare_ledger", spy)
    cache: dict = {}
    longer = Proposal(
        "spaylater", TODAY, tuple(Instalment(i + 1, date(2025, 6 + i, 12), 10000) for i in range(6))
    )
    build(cache=cache)
    build(cache=cache, proposal=longer)
    build(cache=cache)

    assert len(calls) == 1
