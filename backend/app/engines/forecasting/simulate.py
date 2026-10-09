"""Monte Carlo of the monthly margin (plan P4, task C5; PRD 3.1, D-27).

There is no starting balance. For each simulated path and each month of the horizon:

    margin = known income + forecast unconfirmed income
             - known bills - BNPL instalments (including checkout payments)
             - forecast discretionary spend

The cumulative margin starts at RM0 at the START OF THE CURRENT MONTH ("no savings assumed") and
accumulates month by month; what has already come in and gone out this month is the
`month_to_date_sen` net, so a student paid on the 1st is not treated as if that income never
arrived (ADR D-33 amends D-27's "RM0 today").
P(shortfall) is the share of paths whose cumulative margin is below RM0 at ANY month-end of the
horizon: the plan could not be paid from income alone. Each path adds block-resampled past errors
of the model to its point forecast, so it is centred on the model's own record (a level bias the
model has shown is carried into the paths and corrected, not hidden) and the bands widen when the
history is noisy. A week's value is split across months by days, and the part of the current
week that is already in the past is not counted.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

import numpy as np

from app.engines.forecasting.flows import MonthFlows, month_key
from app.engines.forecasting.series import WeeklySeries

DAYS_PER_WEEK = 7
MAX_WEEKS = 52  # the default horizon cap (the dashboard forecast looks 3 months ahead anyway)
# A risk check simulates to the last instalment of the proposed plan (ADR D-36, which replaces the
# 52-week cap of ASSUMED 2): the longest plan the app allows is 36 monthly instalments, about 157
# weeks, plus a month of lag to the first one and the rounding up to a whole month.
RISK_CHECK_MAX_WEEKS = 180
BOOTSTRAP_BLOCK = 4  # weeks
DEFAULT_PATHS = 1000
SAFE_BELOW = 0.10  # pre-registered before training: Safe < 0.10, Caution < 0.30, At Risk >= 0.30
CAUTION_BELOW = 0.30
PERCENTILES = (10, 50, 90)


class Forecaster(Protocol):
    name: str

    def forecast(self, history: np.ndarray, horizon: int, start: date) -> np.ndarray: ...


@dataclass(frozen=True)
class Simulation:
    months: list[str]
    monthly_margin_p10_sen: list[int]
    monthly_margin_p50_sen: list[int]
    monthly_margin_p90_sen: list[int]
    cumulative_margin_p10_sen: list[int]
    cumulative_margin_p50_sen: list[int]
    cumulative_margin_p90_sen: list[int]
    p_shortfall: float
    worst_month: str | None  # the month the running total is most often negative in
    p_negative_by_month: list[float]
    weeks: int
    horizon_capped: bool
    bootstrap: str  # "paths" | "block" | "plain" | "none" | "fallback": how errors were resampled
    # summaries Engine 2 uses as features (sen): the typical simulated week of discretionary spend
    # (median and 90th percentile across paths, averaged over the weeks in the horizon) and the
    # downside monthly income (10th percentile across paths, averaged over the months)
    weekly_spend_p50_sen: float = 0.0
    weekly_spend_p90_sen: float = 0.0
    monthly_income_p10_sen: float = 0.0
    # sensitivity only (ASSUMED 4): the share of paths in which ANY single month's margin is
    # negative, instead of the running total. The label and every band use `p_shortfall`.
    p_shortfall_monthly: float = 0.0


def forecaster_for(forecaster: Forecaster, kind: str) -> Forecaster:
    """One model per series kind when it has them (the LSTM), else the same model for both."""
    chooser = getattr(forecaster, "for_kind", None)
    return chooser(kind) if chooser else forecaster


def band(p_shortfall: float) -> str:
    if p_shortfall < SAFE_BELOW:
        return "Safe"
    return "Caution" if p_shortfall < CAUTION_BELOW else "At Risk"


def health_score(p_shortfall: float) -> int:
    return round((1 - p_shortfall) * 100)


def block_bootstrap(
    residuals: np.ndarray, length: int, paths: int, block: int, rng: np.random.Generator
) -> np.ndarray:
    """`paths` sequences of `length` resampled residuals, in runs of `block` consecutive ones."""
    if len(residuals) == 0:
        return np.zeros((paths, length))
    if len(residuals) < 2 * block:
        return rng.choice(residuals, size=(paths, length))
    blocks = math.ceil(length / block)
    starts = rng.integers(0, len(residuals) - block + 1, size=(paths, blocks))
    index = starts[:, :, None] + np.arange(block)
    return residuals[index].reshape(paths, blocks * block)[:, :length]


def path_bootstrap(
    error_paths: np.ndarray, length: int, paths: int, rng: np.random.Generator
) -> np.ndarray:
    """`paths` sequences of `length` weeks, each built by joining whole past error paths.

    An error path is how wrong the model was, week by week, from one past origin. Joining whole
    paths keeps a wrong level wrong for as long as it really stayed wrong, which is what makes a
    long-horizon band wide enough.
    """
    if error_paths.size == 0:
        return np.zeros((paths, length))
    rows, width = error_paths.shape
    pieces = math.ceil(length / width)
    pick = rng.integers(0, rows, size=(paths, pieces))
    return error_paths[pick].reshape(paths, pieces * width)[:, :length]


def _draw(errors: np.ndarray, length: int, paths: int, rng: np.random.Generator) -> np.ndarray:
    if errors.ndim == 2:
        return path_bootstrap(errors, length, paths, rng)
    return block_bootstrap(errors, length, paths, BOOTSTRAP_BLOCK, rng)


def _bootstrap_kind(*residuals: np.ndarray, fallback: bool = False) -> str:
    if fallback:
        return "fallback"
    if all(r.size == 0 for r in residuals):
        return "none"
    if all(r.ndim == 2 for r in residuals if r.size):
        return "paths" if all(len(r) >= 2 for r in residuals if r.size) else "plain"
    return "block" if all(len(r) >= 2 * BOOTSTRAP_BLOCK for r in residuals if len(r)) else "plain"


def _month_weights(
    first_monday: date, weeks: int, start: date, end: date, months: list[str]
) -> np.ndarray:
    """Share of each forecast week that falls in each month, counting only days in [start, end]."""
    position = {m: i for i, m in enumerate(months)}
    weights = np.zeros((weeks, len(months)))
    for week in range(weeks):
        for offset in range(DAYS_PER_WEEK):
            day = first_monday + timedelta(days=DAYS_PER_WEEK * week + offset)
            if start <= day <= end and month_key(day) in position:
                weights[week, position[month_key(day)]] += 1 / DAYS_PER_WEEK
    return weights


def _percentiles(values: np.ndarray) -> list[list[int]]:
    return [[int(round(v)) for v in np.percentile(values, q, axis=0)] for q in PERCENTILES]


def simulate(
    series: WeeklySeries,
    known: Mapping[str, MonthFlows],
    forecaster: Forecaster,
    spend_errors: np.ndarray,
    income_errors: np.ndarray,
    start: date,
    end: date,
    paths: int = DEFAULT_PATHS,
    seed: int = 0,
    month_to_date_sen: int = 0,
    fallback_errors: bool = False,
    max_weeks: int = MAX_WEEKS,
) -> Simulation:
    if series.start is None or series.weeks == 0:
        raise ValueError("a forecast needs at least one complete week of history")
    first_monday = series.start + timedelta(days=DAYS_PER_WEEK * series.weeks)
    end = _month_end(month_key(end))  # whole months only: a partial last month would miss income
    # that lands later in it and invent a month-end shortfall
    needed = math.ceil(((end - first_monday).days + 1) / DAYS_PER_WEEK)
    weeks = max(1, min(needed, max_weeks))
    capped = needed > max_weeks
    covered_until = first_monday + timedelta(days=DAYS_PER_WEEK * weeks - 1)
    last_day = min(end, covered_until)
    months = [
        m
        for m in sorted(known)
        if not capped or _month_end(m) <= covered_until or m == month_key(start)
    ]

    rng = np.random.default_rng(seed)
    spend_point = np.clip(
        forecaster_for(forecaster, "spend").forecast(
            series.spend.astype(float), weeks, series.start
        ),
        0,
        None,
    )
    income_point = np.clip(
        forecaster_for(forecaster, "income").forecast(
            series.income.astype(float), weeks, series.start
        ),
        0,
        None,
    )
    spend = np.clip(spend_point + _draw(spend_errors, weeks, paths, rng), 0, None)
    income = np.clip(income_point + _draw(income_errors, weeks, paths, rng), 0, None)

    weights = _month_weights(first_monday, weeks, start, last_day, months)
    flows = [known[m] for m in months]
    fixed = np.array([f.income_sen - f.bills_sen - f.instalments_sen for f in flows], dtype=float)
    margin = fixed + income @ weights - spend @ weights
    margin[:, 0] += month_to_date_sen  # actual net of the days of this month already gone
    cumulative = np.cumsum(margin, axis=1)
    negative = cumulative < 0
    p_negative = negative.mean(axis=0)
    p_shortfall = float(negative.any(axis=1).mean())
    p_shortfall_monthly = float((margin < 0).any(axis=1).mean())

    in_horizon = weights.sum(axis=1) > 0
    spend_weeks = spend[:, in_horizon]
    monthly_income = np.array([f.income_sen for f in flows], dtype=float) + income @ weights
    monthly = _percentiles(margin)
    running = _percentiles(cumulative)
    worst = months[int(np.argmax(p_negative))] if p_shortfall > 0 else None
    return Simulation(
        months=months,
        monthly_margin_p10_sen=monthly[0],
        monthly_margin_p50_sen=monthly[1],
        monthly_margin_p90_sen=monthly[2],
        cumulative_margin_p10_sen=running[0],
        cumulative_margin_p50_sen=running[1],
        cumulative_margin_p90_sen=running[2],
        p_shortfall=p_shortfall,
        worst_month=worst,
        p_negative_by_month=[float(p) for p in p_negative],
        weeks=weeks,
        horizon_capped=capped,
        bootstrap=_bootstrap_kind(spend_errors, income_errors, fallback=fallback_errors),
        weekly_spend_p50_sen=float(np.percentile(spend_weeks, 50, axis=0).mean()),
        weekly_spend_p90_sen=float(np.percentile(spend_weeks, 90, axis=0).mean()),
        monthly_income_p10_sen=float(np.percentile(monthly_income, 10, axis=0).mean()),
        p_shortfall_monthly=p_shortfall_monthly,
    )


def _month_end(key: str) -> date:
    year, month = int(key[:4]), int(key[5:])
    following = date(year + (month == 12), month % 12 + 1, 1)
    return following - timedelta(days=1)
