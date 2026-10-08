"""Scale-free forecast metrics (plan P3, task B3).

Percentage errors explode near zero, and a personal-finance series is zero or near zero often
(v1 lesson), so errors are scaled by the in-sample one-step naive error (Hyndman and Koehler).
A history with no variation has no scale; the metric is then NaN ("not defined") and the caller
skips it, rather than reporting a misleading zero.
"""

import math

import numpy as np


def naive_scale(history: np.ndarray) -> float | None:
    """Mean absolute one-step naive error over the training history, or None if it is zero."""
    if len(history) < 2:
        return None
    scale = float(np.mean(np.abs(np.diff(history))))
    return scale if scale > 0 else None


def mase(actual: np.ndarray, forecast: np.ndarray, scale: float | None) -> float:
    if scale is None:
        return math.nan
    return float(np.mean(np.abs(actual - forecast)) / scale)


def rmsse(actual: np.ndarray, forecast: np.ndarray, history: np.ndarray) -> float:
    if len(history) < 2:
        return math.nan
    naive_mse = float(np.mean(np.diff(history) ** 2))
    if naive_mse == 0:
        return math.nan
    return math.sqrt(float(np.mean((actual - forecast) ** 2)) / naive_mse)


def interval_coverage(actual: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    return float(np.mean((actual >= lower) & (actual <= upper)))


def interval_width(lower: np.ndarray, upper: np.ndarray) -> float:
    return float(np.mean(upper - lower))


def cumulative_margin_error(
    income_actual: np.ndarray,
    income_forecast: np.ndarray,
    spend_actual: np.ndarray,
    spend_forecast: np.ndarray,
    horizon: int,
) -> float:
    """Absolute error of the running income-minus-spend total after `horizon` weeks.

    This mirrors the product: Engine 2's label is the probability that the *cumulative* margin
    goes negative, so the quantity worth forecasting well is the running total, not each week.
    """
    if horizon > min(len(income_forecast), len(spend_forecast)) or horizon < 1:
        raise ValueError(f"horizon {horizon} is outside the forecast length")
    actual = np.cumsum(income_actual[:horizon] - spend_actual[:horizon])[-1]
    forecast = np.cumsum(income_forecast[:horizon] - spend_forecast[:horizon])[-1]
    return float(abs(actual - forecast))
