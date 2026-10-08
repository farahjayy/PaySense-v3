"""One call from a ledger to a forecast (plan P4, tasks C5-C7). No database access in here: the
caller loads the user's own rows (user-scoped, D-03) and passes them in.

Everything before `forecast_from` (the Monday after the last complete logged week) is ACTUAL:
the month-to-date net comes from the ledger. Everything from `forecast_from` on is rules and
model: known flows placed on their dates and the forecast variable spending and income. This is
what makes a ledger that stopped being updated three weeks ago be forecast from where it stopped,
instead of treating the silent weeks as zero spending.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.domain.flows import as_date, month_summary
from app.domain.merchants import normalise_merchant
from app.domain.schedule import add_months
from app.engines.forecasting.completeness import SuspectMonth, assess
from app.engines.forecasting.errors import mean_forecast_errors, rolling_error_paths, widen
from app.engines.forecasting.flows import ProposedPlan, known_flows
from app.engines.forecasting.series import build_weekly_series
from app.engines.forecasting.simulate import (
    DEFAULT_PATHS,
    Forecaster,
    Simulation,
    band,
    forecaster_for,
    health_score,
    simulate,
)

DASHBOARD_MONTHS = 3
MIN_SERIES_WEEKS = 17  # about four months of complete weeks: enough to score the model at all
MIN_ERROR_PATHS = 2  # fewer past error paths than this and the bands come from the fallback
STALE_AFTER_DAYS = 14  # the ledger has not been updated for this long: warn
# ASSUMED: the error record of a short history understates future uncertainty (it cannot see a
# level that drifts further than it has so far), so recorded errors are widened by this factor.
# Chosen from a simulation of drifting weekly series; coverage is still below nominal for short
# histories, which the serving report states rather than claims otherwise.
ERROR_INFLATION = 1.5
KIND_TO_TYPE = {"income": "income", "bill": "expense"}


@dataclass(frozen=True)
class Forecast:
    status: str  # "ok" | "locked"
    months_of_history: int
    suspect_months: list[SuspectMonth]
    series_weeks: int
    lock_reason: str | None
    simulation: Simulation | None
    band: str | None
    health_score: int | None
    data_through: date | None = None  # the last day anything was logged
    stale_days: int | None = None
    unmatched_items: tuple[str, ...] = ()  # confirmed items that match no logged transaction


def month_to_date_net(rows: list[Mapping[str, Any]], first_day: date, until: date) -> int:
    """Net of what really happened from `first_day` up to (not including) `until`: income minus
    spend, refunds netted, savings excluded."""
    so_far = [r for r in rows if first_day <= as_date(r["date"]) < until]
    return sum(m.net_sen for m in month_summary(so_far))


def horizon_end(today: date, months: int = DASHBOARD_MONTHS) -> date:
    """Last day of the month `months - 1` months after the current one."""
    return add_months(date(today.year, today.month, 1), months) - timedelta(days=1)


def _match_text(item: Mapping[str, Any]) -> str:
    return item.get("match_text") or item["name"]


def _unmatched(rows: list[Mapping[str, Any]], items: list[Mapping[str, Any]]) -> tuple[str, ...]:
    seen = {(r["type"], normalise_merchant(r.get("description"))) for r in rows}
    return tuple(
        item["name"]
        for item in items
        if (KIND_TO_TYPE[item["kind"]], normalise_merchant(_match_text(item))) not in seen
    )


def _locked(reason: str, months: int, suspects: list[SuspectMonth], weeks: int = 0) -> Forecast:
    return Forecast("locked", months, suspects, weeks, reason, None, None, None)


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
    rows = [r for r in rows if as_date(r["date"]) <= today]  # nothing from the future
    items, plans = list(items), list(plans)
    completeness = assess(rows, today)
    if completeness.status == "locked":
        return _locked("needs_four_months", completeness.months_of_history, [])
    months, suspects = completeness.months_of_history, completeness.suspect_months

    confirmed = [i for i in items if i.get("active", True)]
    covered = [(KIND_TO_TYPE[i["kind"]], _match_text(i)) for i in confirmed]
    series = build_weekly_series(rows, today, covered)
    if series.weeks == 0:  # e.g. only savings, plan payments or confirmed items so far
        return _locked("no_usable_history", months, suspects)
    if series.weeks < MIN_SERIES_WEEKS:
        return _locked("needs_four_months", months, suspects, series.weeks)

    forecast_from = series.start + timedelta(days=7 * series.weeks)
    horizon = max(end or horizon_end(today), forecast_from)
    known = known_flows(confirmed, plans, forecast_from, horizon, proposed)
    spend_errors = rolling_error_paths(
        series.spend, series.start, forecaster_for(forecaster, "spend")
    )
    income_errors = rolling_error_paths(
        series.income, series.start, forecaster_for(forecaster, "income")
    )
    fallback = len(spend_errors) < MIN_ERROR_PATHS or len(income_errors) < MIN_ERROR_PATHS
    if fallback:  # too short to score the model: use the series' own spread, never zero noise
        spend_errors = mean_forecast_errors(series.spend)
        income_errors = mean_forecast_errors(series.income)
    spend_errors = widen(spend_errors, ERROR_INFLATION)
    income_errors = widen(income_errors, ERROR_INFLATION)
    first_of_month = date(forecast_from.year, forecast_from.month, 1)
    simulation = simulate(
        series,
        known,
        forecaster,
        spend_errors,
        income_errors,
        forecast_from,
        horizon,
        paths,
        seed,
        month_to_date_sen=month_to_date_net(rows, first_of_month, forecast_from),
        fallback_errors=fallback,
    )
    latest = max(as_date(r["date"]) for r in rows)
    return Forecast(
        status="ok",
        months_of_history=months,
        suspect_months=suspects,
        series_weeks=series.weeks,
        lock_reason=None,
        simulation=simulation,
        band=band(simulation.p_shortfall),
        health_score=health_score(simulation.p_shortfall),
        data_through=latest,
        stale_days=(today - latest).days,
        unmatched_items=_unmatched(rows, confirmed),
    )
