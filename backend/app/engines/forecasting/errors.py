"""A user's own rolling-origin forecast errors (plan P4, task C6).

The residual bootstrap needs a record of how wrong the served model has been on THIS user's
series. At each past origin the model sees only the history before it, forecasts the next
`horizon` weeks, and the whole signed error PATH (actual minus forecast, week by week) is kept.
Keeping paths rather than a flat pile of errors preserves how errors persist from one week to the
next: a level that is wrong stays wrong for a while, and resampling single weeks as if independent
would make the bands far too narrow over a long horizon. Only the latest origins are used, which
bounds the cost of a request.
"""

import numpy as np

from app.engines.forecasting.simulate import Forecaster

DEFAULT_HORIZON = 8  # weeks scored at each origin, and the length of a resampled error path
DEFAULT_MIN_TRAIN = 8
DEFAULT_STRIDE = 2
DEFAULT_MAX_ORIGINS = 10


def rolling_error_paths(
    values: np.ndarray,
    start,
    forecaster: Forecaster,
    horizon: int = DEFAULT_HORIZON,
    min_train: int = DEFAULT_MIN_TRAIN,
    stride: int = DEFAULT_STRIDE,
    max_origins: int = DEFAULT_MAX_ORIGINS,
) -> np.ndarray:
    """Signed error paths, shape (origins, horizon), from up to `max_origins` latest origins;
    zero rows if the series is too short for even one."""
    values = np.asarray(values, dtype=float)
    origins = list(range(min_train, len(values) - horizon + 1, stride))[-max_origins:]
    paths = []
    for origin in origins:
        history = values[:origin]  # nothing after the origin is ever shown to the model
        forecast = np.clip(forecaster.forecast(history, horizon, start), 0, None)
        paths.append(values[origin : origin + horizon] - forecast)
    return np.array(paths).reshape(len(paths), horizon)


def rolling_errors(
    values: np.ndarray,
    start,
    forecaster: Forecaster,
    horizon: int = 4,
    min_train: int = DEFAULT_MIN_TRAIN,
    stride: int = DEFAULT_STRIDE,
    max_origins: int = DEFAULT_MAX_ORIGINS,
) -> np.ndarray:
    """The same errors pooled into one flat sequence (kept for the simple cases and tests)."""
    return rolling_error_paths(
        values, start, forecaster, horizon, min_train, stride, max_origins
    ).ravel()


def mean_forecast_errors(values: np.ndarray) -> np.ndarray:
    """A last-resort error scale for a series too short to score: how far each week sits from the
    series' own mean, as a single path. Used so the bands are honest rather than zero-width."""
    values = np.asarray(values, dtype=float)
    return (values - values.mean()).reshape(1, -1) if len(values) else np.zeros((0, 1))


def widen(error_paths: np.ndarray, factor: float) -> np.ndarray:
    """Spread the recorded errors by `factor` around their own mean: the bands get wider but the
    centring on the model's record (its level bias) is left exactly where it was."""
    if error_paths.size == 0:
        return error_paths
    centre = error_paths.mean()
    return centre + factor * (error_paths - centre)
