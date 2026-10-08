"""The benchmarks every comparison must include (D-05, D-06): naive and moving average."""

from datetime import date

import numpy as np


class Naive:
    """Repeat the last observed week."""

    name = "naive"

    def forecast(self, history: np.ndarray, horizon: int, start: date) -> np.ndarray:
        return np.full(horizon, history[-1], dtype=float)


class MovingAverage:
    """Repeat the mean of the last `window` weeks.

    The window is a fixed configuration (4 and 13 weeks are both run), not tuned on test origins.
    """

    def __init__(self, window: int) -> None:
        if window < 1:
            raise ValueError("window must be at least 1")
        self.window = window
        self.name = f"ma{window}"

    def forecast(self, history: np.ndarray, horizon: int, start: date) -> np.ndarray:
        return np.full(horizon, float(np.mean(history[-self.window :])), dtype=float)
