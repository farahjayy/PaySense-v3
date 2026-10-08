"""The interface every candidate implements (plan P3, task B4).

A forecaster sees only the history it is handed and returns point forecasts. The harness never
special-cases a model, so a benchmark and a neural network are compared by identical code.
Prediction intervals are not the model's job: the harness builds the same empirical-error interval
for every candidate (see harness.py), which keeps coverage comparable.
"""

from datetime import date
from typing import Protocol

import numpy as np


class Forecaster(Protocol):
    name: str

    def forecast(self, history: np.ndarray, horizon: int, start: date) -> np.ndarray:
        """Point forecasts for the `horizon` weeks after `history` (non-negative amounts).

        `start` is the Monday of `history[0]`, for models that use the calendar.
        """
        ...
