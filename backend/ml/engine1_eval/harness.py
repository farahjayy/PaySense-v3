"""Expanding-window rolling-origin evaluation (plan P3, task B4).

At each origin the model is handed `values[:origin]` as a read-only array and nothing else, so it
cannot read the future. Intervals are built identically for every model from that model's own
earlier errors, using only errors whose target week is already observed at the origin.
(The 4-week moving-block bootstrap in the product is for simulating whole paths in P4; for
comparing marginal coverage across models the per-step empirical error quantile is the standard,
simpler choice.)
"""

import time
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from ml.engine1_eval.data import DAYS_PER_WEEK, Series
from ml.engine1_eval.forecaster import Forecaster
from ml.engine1_eval.metrics import (
    cumulative_margin_error,
    interval_coverage,
    interval_width,
    mase,
    naive_scale,
    rmsse,
)


@dataclass(frozen=True)
class EvalConfig:
    horizon: int = 13
    report_horizons: tuple[int, ...] = (1, 4, 13)
    min_train: int = 26
    stride: int = 4
    max_origins: int | None = None
    interval_level: float = 0.8
    min_interval_errors: int = 8
    history_limit: int | None = None  # models see only the last N weeks (short-history study)
    first_origin_date: date | None = None  # no origin earlier than this week (see _origins)


@dataclass
class SeriesEvaluation:
    rows: list[dict] = field(default_factory=list)
    skipped: int = 0  # origins whose history had no variation, so no scaled error exists
    seconds: float = 0.0  # wall-clock spent in the model (kept out of the rows: not reproducible)


def rolling_origins(
    length: int, min_train: int, horizon: int, stride: int, max_origins: int | None = None
) -> list[int]:
    origins = list(range(min_train, length - horizon + 1, stride))
    return origins[-max_origins:] if max_origins else origins


def _origins(length: int, series_start: date, config: EvalConfig) -> list[int]:
    """Origins for one series. `first_origin_date` keeps every model on the same, later part of the
    calendar, so a global model trained on earlier weeks of other series is never tested on the
    weeks it was trained on (calendar effects such as exam weeks are shared across series)."""
    first = config.min_train
    if config.first_origin_date is not None:
        days = (config.first_origin_date - series_start).days
        first = max(first, -(-days // DAYS_PER_WEEK))  # ceiling division
    return rolling_origins(length, first, config.horizon, config.stride, config.max_origins)


def _history_start(series_start: date, origin: int, history: np.ndarray) -> date:
    return series_start + timedelta(days=DAYS_PER_WEEK * (origin - len(history)))


def _history(values: np.ndarray, origin: int, limit: int | None = None) -> np.ndarray:
    history = values[max(0, origin - limit) if limit else 0 : origin].copy()
    history.flags.writeable = False
    return history


class _ErrorLedger:
    """A model's signed errors per forecast step, usable only once their target is observed."""

    def __init__(self, horizon: int) -> None:
        self._targets: list[list[int]] = [[] for _ in range(horizon)]
        self._errors: list[list[float]] = [[] for _ in range(horizon)]

    def add(self, origin: int, errors: np.ndarray) -> None:
        for step, error in enumerate(errors):
            self._targets[step].append(origin + step)
            self._errors[step].append(float(error))

    def bounds(
        self, origin: int, forecast: np.ndarray, level: float, minimum: int
    ) -> tuple[np.ndarray, np.ndarray] | None:
        tail = (1 - level) / 2
        lower, upper = np.empty(len(forecast)), np.empty(len(forecast))
        for step in range(len(forecast)):
            known = [
                e
                for t, e in zip(self._targets[step], self._errors[step], strict=True)
                if t < origin
            ]
            if len(known) < minimum:
                return None
            low, high = np.quantile(known, [tail, 1 - tail])
            lower[step] = max(forecast[step] + low, 0.0)
            upper[step] = max(forecast[step] + high, 0.0)
        return lower, upper


def _forecast(model: Forecaster, history: np.ndarray, horizon: int, start: date) -> np.ndarray:
    forecast = np.asarray(model.forecast(history, horizon, start), dtype=float)
    if forecast.shape != (horizon,):
        raise ValueError(f"{model.name} returned {forecast.shape}, expected ({horizon},)")
    return forecast


def evaluate_series(series: Series, model: Forecaster, config: EvalConfig) -> SeriesEvaluation:
    result = SeriesEvaluation()
    ledger = _ErrorLedger(config.horizon)
    last = config.horizon
    for origin in _origins(len(series), series.start, config):
        history = _history(series.values, origin, config.history_limit)
        began = time.perf_counter()
        forecast = _forecast(
            model, history, config.horizon, _history_start(series.start, origin, history)
        )
        result.seconds += time.perf_counter() - began
        actual = series.values[origin : origin + config.horizon]
        bounds = ledger.bounds(origin, forecast, config.interval_level, config.min_interval_errors)
        ledger.add(origin, actual - forecast)

        scale = naive_scale(history)
        if scale is None:
            result.skipped += 1
            continue
        row = {
            "series_id": series.series_id,
            "kind": series.kind,
            "source": series.source,
            "model": model.name,
            "origin": origin,
            "train_len": len(history),
            "scale": scale,
        }
        for h in config.report_horizons:
            row[f"mase_{h}"] = mase(actual[:h], forecast[:h], scale)
        row[f"rmsse_{last}"] = rmsse(actual, forecast, history)
        if bounds is None:
            row[f"coverage_{last}"] = row[f"width_{last}"] = float("nan")
        else:
            row[f"coverage_{last}"] = interval_coverage(actual, *bounds)
            row[f"width_{last}"] = interval_width(*bounds) / scale
        result.rows.append(row)
    return result


def evaluate_pair(
    spend: Series, income: Series, model: Forecaster, config: EvalConfig
) -> list[dict]:
    """Cumulative-margin error: how well the model forecasts the running income-minus-spend."""
    if spend.start != income.start or len(spend) != len(income):
        raise ValueError("spend and income series must cover the same weeks")
    rows = []
    for origin in _origins(len(spend), spend.start, config):
        spend_history, income_history = (
            _history(spend.values, origin, config.history_limit),
            _history(income.values, origin, config.history_limit),
        )
        start = _history_start(spend.start, origin, spend_history)
        scale = naive_scale(income_history - spend_history)
        if scale is None:
            continue
        spend_forecast = _forecast(model, spend_history, config.horizon, start)
        income_forecast = _forecast(model, income_history, config.horizon, start)
        spend_actual = spend.values[origin : origin + config.horizon]
        income_actual = income.values[origin : origin + config.horizon]
        row = {
            "series_id": spend.series_id,
            "source": spend.source,
            "model": model.name,
            "origin": origin,
            "scale": scale,
        }
        for h in config.report_horizons:
            error = cumulative_margin_error(
                income_actual, income_forecast, spend_actual, spend_forecast, h
            )
            row[f"margin_{h}"] = error / scale
        rows.append(row)
    return rows
