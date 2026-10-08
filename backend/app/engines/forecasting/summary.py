"""From a ledger and a proposed plan to the Engine 2 inputs and the simulated label (plan P5, D2).

One function used by training (`ml/engine2_train`) and, in P6, by serving: the label is the
Engine 1 simulation with the proposed plan, the features are computed by `risk/features.py` from
the same objects. Nothing here reads the generator's answer keys.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median
from typing import Any, Protocol

from app.domain.flows import as_date, month_summary
from app.engines.forecasting.flows import ProposedPlan
from app.engines.forecasting.service import Forecast, build_forecast, horizon_end
from app.engines.forecasting.simulate import Forecaster
from app.engines.risk.features import (
    Commitments,
    Engine1Summary,
    FeatureInputs,
    PlanInput,
)

RECENT_MONTHS = 3  # months averaged for the expected income
COMMITMENT_MONTHS = 3  # existing BNPL obligations are spread over this many months
WEEKS_PER_YEAR = 52
MONTHS_PER_YEAR = 12
DAYS_PER_YEAR = 365
SEMESTERS_PER_YEAR = 2


class ProposalLike(ProposedPlan, Protocol):
    provider: str
    upfront_sen: int
    monthly_fee_rate_pct: float
    total_payable_sen: int


@dataclass(frozen=True)
class Built:
    inputs: FeatureInputs
    without: Forecast
    with_plan: Forecast

    @property
    def p_with(self) -> float:
        return self.with_plan.simulation.p_shortfall

    @property
    def p_without(self) -> float:
        return self.without.simulation.p_shortfall


def expected_monthly_income(rows: Iterable[Mapping[str, Any]], today: date) -> int:
    """Mean income of the latest complete months (up to three); 0 when there is none."""
    current = today.strftime("%Y-%m")
    complete = [m for m in month_summary(rows) if m.month < current][-RECENT_MONTHS:]
    return round(sum(m.income_sen for m in complete) / len(complete)) if complete else 0


def monthly_equivalent_sen(item: Mapping[str, Any]) -> float:
    amount = int(item["amount_sen"])
    cadence = item["cadence"]
    if cadence == "monthly":
        return float(amount)
    if cadence == "weekly":
        return amount * WEEKS_PER_YEAR / MONTHS_PER_YEAR
    if cadence == "biweekly":
        return amount * (WEEKS_PER_YEAR / 2) / MONTHS_PER_YEAR
    if cadence == "semester":
        return amount * SEMESTERS_PER_YEAR / MONTHS_PER_YEAR
    return amount * DAYS_PER_YEAR / int(item["custom_interval_days"]) / MONTHS_PER_YEAR


def _commitments(
    items: list[Mapping[str, Any]],
    plans: list[Mapping[str, Any]],
    provider: str,
    limit: int | None,
    today: date,
) -> Commitments:
    soon = today + timedelta(days=30 * COMMITMENT_MONTHS)
    owed = due_soon = by_provider = active = 0
    for plan in plans:
        unpaid = [i for i in plan["installments"] if not i["is_paid"]]
        if not unpaid:
            continue
        active += 1
        amount = sum(int(i["amount_sen"]) for i in unpaid)
        owed += amount
        if plan.get("provider") == provider:
            by_provider += amount
        due_soon += sum(int(i["amount_sen"]) for i in unpaid if as_date(i["due_date"]) <= soon)
    bills = sum(monthly_equivalent_sen(i) for i in items if i["kind"] == "bill" and i["active"])
    return Commitments(
        monthly_bnpl_sen=round(due_soon / COMMITMENT_MONTHS),
        monthly_debt_like_bills_sen=round(bills),
        active_plans=active,
        outstanding_bnpl_sen=owed,
        provider_outstanding_sen=by_provider,
        provider_limit_sen=limit,
    )


def _engine1(without: Forecast) -> Engine1Summary:
    sim = without.simulation
    return Engine1Summary(
        disc_weekly_p50_sen=sim.weekly_spend_p50_sen,
        disc_weekly_p90_sen=sim.weekly_spend_p90_sen,
        disc_volatility_sen=without.spend_error_std_sen,
        margin_monthly_p50_without_sen=float(median(sim.monthly_margin_p50_sen)),
        margin_cum_p10_without_sen=float(min(sim.cumulative_margin_p10_sen)),
        income_p10_monthly_sen=sim.monthly_income_p10_sen,
    )


def build_feature_inputs(
    rows: Iterable[Mapping[str, Any]],
    items: Iterable[Mapping[str, Any]],
    plans: Iterable[Mapping[str, Any]],
    proposal: ProposalLike,
    provider_limits: Mapping[str, int | None],
    today: date,
    forecaster: Forecaster,
    seed: int = 0,
    paths: int = 1000,
) -> Built | None:
    """Engine 2 inputs and both simulations, or None if the ledger is locked.

    The two simulations share one seed, so they draw the same random paths and the purchase can
    only make things worse, never better, by chance.
    """
    rows, items, plans = list(rows), list(items), list(plans)
    plan_end = max((i.due_date for i in proposal.instalments), default=today)
    end = max(horizon_end(today), plan_end)
    common = dict(rows=rows, items=items, plans=plans, today=today, forecaster=forecaster)
    without = build_forecast(**common, end=end, paths=paths, seed=seed)
    if without.status != "ok":
        return None
    with_plan = build_forecast(**common, proposed=proposal, end=end, paths=paths, seed=seed)
    inputs = FeatureInputs(
        plan=PlanInput(
            instalment_amounts_sen=tuple(i.amount_sen for i in proposal.instalments),
            monthly_fee_rate_pct=float(proposal.monthly_fee_rate_pct),
            financed_payable_sen=int(proposal.total_payable_sen),
            upfront_sen=int(proposal.upfront_sen),
        ),
        commitments=_commitments(
            items, plans, proposal.provider, provider_limits.get(proposal.provider), today
        ),
        engine1=_engine1(without),
        expected_monthly_income_sen=expected_monthly_income(rows, today),
    )
    return Built(inputs, without, with_plan)
