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

import numpy as np

from app.domain.flows import as_date, month_summary
from app.domain.merchants import normalise_merchant
from app.domain.schedule import add_months
from app.engines.forecasting.completeness import SuspectMonth, assess
from app.engines.forecasting.errors import mean_forecast_errors, rolling_error_paths, widen
from app.engines.forecasting.flows import ProposedPlan, known_flows, unlogged_occurrences_net
from app.engines.forecasting.series import build_weekly_series
from app.engines.forecasting.simulate import (
    DEFAULT_PATHS,
    MAX_WEEKS,
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
    spend_error_std_sen: float = 0.0  # spread of the model's own weekly spend errors


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


@dataclass(frozen=True)
class LedgerPrep:
    """Everything about a ledger that does not depend on the plan being tried: it is read once and
    reused for every candidate plan in a risk check."""

    rows: list[Mapping[str, Any]]
    confirmed: list[Mapping[str, Any]]
    months: int
    suspects: list[SuspectMonth]
    series: Any
    forecast_from: date
    spend_errors: np.ndarray
    income_errors: np.ndarray
    fallback: bool
    error_std: float
    month_to_date_sen: int
    latest: date
    unmatched: tuple[str, ...]


def prepare_ledger(
    rows: Iterable[Mapping[str, Any]],
    items: Iterable[Mapping[str, Any]],
    today: date,
    forecaster: Forecaster,
) -> LedgerPrep | Forecast:
    """The plan-independent half of a forecast, or the locked forecast if the ledger is too thin."""
    rows = [r for r in rows if as_date(r["date"]) <= today]  # nothing from the future
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
    spend_errors = rolling_error_paths(
        series.spend, series.start, forecaster_for(forecaster, "spend")
    )
    income_errors = rolling_error_paths(
        series.income, series.start, forecaster_for(forecaster, "income")
    )
    fallback = len(spend_errors) < MIN_ERROR_PATHS or len(income_errors) < MIN_ERROR_PATHS
    if fallback:  # too short to score the model: use the series own spread, never zero noise
        spend_errors = mean_forecast_errors(series.spend)
        income_errors = mean_forecast_errors(series.income)
    error_std = float(np.std(spend_errors)) if spend_errors.size else 0.0
    first_of_month = date(forecast_from.year, forecast_from.month, 1)
    return LedgerPrep(
        rows=rows,
        confirmed=confirmed,
        months=months,
        suspects=suspects,
        series=series,
        forecast_from=forecast_from,
        spend_errors=widen(spend_errors, ERROR_INFLATION),
        income_errors=widen(income_errors, ERROR_INFLATION),
        fallback=fallback,
        error_std=error_std,
        month_to_date_sen=month_to_date_net(rows, first_of_month, forecast_from)
        + unlogged_occurrences_net(confirmed, rows, first_of_month, forecast_from),
        latest=max(as_date(r["date"]) for r in rows),
        unmatched=_unmatched(rows, confirmed),
    )


def forecast_prepared(
    prep: LedgerPrep,
    plans: Iterable[Mapping[str, Any]],
    today: date,
    forecaster: Forecaster,
    proposed: ProposedPlan | None = None,
    end: date | None = None,
    paths: int = DEFAULT_PATHS,
    seed: int = 0,
    max_weeks: int = MAX_WEEKS,
) -> Forecast:
    """The plan-dependent half: known flows for this plan, then the simulation."""
    horizon = max(end or horizon_end(today), prep.forecast_from)
    known = known_flows(prep.confirmed, list(plans), prep.forecast_from, horizon, proposed)
    simulation = simulate(
        prep.series,
        known,
        forecaster,
        prep.spend_errors,
        prep.income_errors,
        prep.forecast_from,
        horizon,
        paths,
        seed,
        month_to_date_sen=prep.month_to_date_sen,
        fallback_errors=prep.fallback,
        max_weeks=max_weeks,
    )
    return Forecast(
        status="ok",
        months_of_history=prep.months,
        suspect_months=prep.suspects,
        series_weeks=prep.series.weeks,
        lock_reason=None,
        simulation=simulation,
        band=band(simulation.p_shortfall),
        health_score=health_score(simulation.p_shortfall),
        data_through=prep.latest,
        stale_days=(today - prep.latest).days,
        unmatched_items=prep.unmatched,
        spend_error_std_sen=prep.error_std,
    )


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
    max_weeks: int = MAX_WEEKS,
) -> Forecast:
    prep = prepare_ledger(rows, items, today, forecaster)
    if isinstance(prep, Forecast):
        return prep
    return forecast_prepared(prep, plans, today, forecaster, proposed, end, paths, seed, max_weeks)
