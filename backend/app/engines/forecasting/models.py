"""Forecasters that run inside the API (plan P4). Benchmarks need nothing beyond numpy."""

from datetime import date

import numpy as np


class Naive:
    """Repeat the last observed week."""

    name = "naive"

    def forecast(self, history: np.ndarray, horizon: int, start: date) -> np.ndarray:
        return np.full(horizon, float(history[-1]))


class MovingAverage:
    """Repeat the mean of the last `window` weeks."""

    def __init__(self, window: int) -> None:
        if window < 1:
            raise ValueError("window must be at least 1")
        self.window = window
        self.name = f"ma{window}"

    def forecast(self, history: np.ndarray, horizon: int, start: date) -> np.ndarray:
        return np.full(horizon, float(np.mean(history[-self.window :])))
