"""A user's own rolling-origin forecast errors (plan P4, task C6).

The residual bootstrap needs a record of how wrong the served model has been on THIS user's
series. At each past origin the model sees only the history before it, forecasts a few weeks, and
the signed errors (actual minus forecast) are kept. Only the latest origins are used, which bounds
the cost of a request. Errors are pooled across the forecast steps.
"""

from datetime import date, timedelta

import numpy as np

from app.engines.forecasting.simulate import Forecaster

DAYS_PER_WEEK = 7
DEFAULT_HORIZON = 4  # weeks scored at each origin
DEFAULT_MIN_TRAIN = 8
DEFAULT_STRIDE = 2
DEFAULT_MAX_ORIGINS = 10


def rolling_errors(
    values: np.ndarray,
    start: date,
    forecaster: Forecaster,
    horizon: int = DEFAULT_HORIZON,
    min_train: int = DEFAULT_MIN_TRAIN,
    stride: int = DEFAULT_STRIDE,
    max_origins: int = DEFAULT_MAX_ORIGINS,
) -> np.ndarray:
    """Signed errors (actual - forecast) from up to `max_origins` latest origins; empty if the
    series is too short for even one."""
    values = np.asarray(values, dtype=float)
    origins = list(range(min_train, len(values) - horizon + 1, stride))[-max_origins:]
    errors: list[float] = []
    for origin in origins:
        history = values[:origin]  # nothing after the origin is ever shown to the model
        forecast = np.clip(forecaster.forecast(history, horizon, start), 0, None)
        errors.extend((values[origin : origin + horizon] - forecast).tolist())
    return np.array(errors)


def week_start_of(start: date, weeks: int) -> date:
    return start + timedelta(days=DAYS_PER_WEEK * weeks)
