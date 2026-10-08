"""One call from a ledger to a forecast (plan P4, tasks C5-C7). No database access in here: the
caller loads the user's own rows (user-scoped, D-03) and passes them in."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.domain.flows import as_date, month_summary
from app.domain.schedule import add_months
from app.engines.forecasting.completeness import SuspectMonth, assess
from app.engines.forecasting.errors import rolling_errors
from app.engines.forecasting.flows import ProposedPlan, known_flows
from app.engines.forecasting.series import build_weekly_series
from app.engines.forecasting.simulate import (
    DEFAULT_PATHS,
    Forecaster,
    Simulation,
    band,
    health_score,
    simulate,
)

DASHBOARD_MONTHS = 3
KIND_TO_TYPE = {"income": "income", "bill": "expense"}


@dataclass(frozen=True)
class Forecast:
    status: str  # "ok" | "locked"
    months_of_history: int
    suspect_months: list[SuspectMonth]
    series_weeks: int
    simulation: Simulation | None
    band: str | None
    health_score: int | None


def month_to_date_net(rows: list[Mapping[str, Any]], today: date) -> int:
    """Net of what already happened this month before today: income minus spend, refunds netted."""
    first = date(today.year, today.month, 1)
    so_far = [r for r in rows if first <= as_date(r["date"]) < today]
    summary = month_summary(so_far)
    return summary[0].net_sen if summary else 0


def horizon_end(today: date, months: int = DASHBOARD_MONTHS) -> date:
    """Last day of the month `months - 1` months after the current one."""
    return add_months(date(today.year, today.month, 1), months) - timedelta(days=1)


def build_forecast(
    rows: Iterable[Mapping[str, Any]],
    items: Iterable[Mapping[str, Any]],
    plans: Iterable[Mapping[str, Any]],
    today: date,
    forecaster: Forecaster,
    proposed: ProposedPlan | None = None,
    end: date | None = None,
    paths: int = DEFAULT_PATHS,
    seed: int = 0,
) -> Forecast:
    rows, items, plans = list(rows), list(items), list(plans)
    completeness = assess(rows, today)
    if completeness.status == "locked":
        return Forecast("locked", completeness.months_of_history, [], 0, None, None, None)

    confirmed = [i for i in items if i.get("active", True)]
    covered = [(KIND_TO_TYPE[i["kind"]], i["name"]) for i in confirmed]
    series = build_weekly_series(rows, today, covered)
    horizon = end or horizon_end(today)
    known = known_flows(confirmed, plans, today, horizon, proposed)
    spend_errors = rolling_errors(series.spend, series.start, forecaster)
    income_errors = rolling_errors(series.income, series.start, forecaster)
    simulation = simulate(
        series, known, forecaster, spend_errors, income_errors, today, horizon, paths, seed,
        month_to_date_sen=month_to_date_net(rows, today),
    )  # fmt: skip
    return Forecast(
        status="ok",
        months_of_history=completeness.months_of_history,
        suspect_months=completeness.suspect_months,
        series_weeks=series.weeks,
        simulation=simulation,
        band=band(simulation.p_shortfall),
        health_score=health_score(simulation.p_shortfall),
    )
