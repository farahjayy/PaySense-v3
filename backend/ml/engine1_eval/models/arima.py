"""AutoARIMA (statsforecast), one of the three literature candidates (D-05)."""

from datetime import date

import numpy as np


class AutoArima:
    """Automatic ARIMA order selection per series, refitted at every origin.

    Weekly personal-finance series have no clean seasonal period (months are 4.3 weeks), so the
    season length is 1. Forecasts are floored at zero: spend and income cannot be negative.
    """

    name = "arima"

    def forecast(self, history: np.ndarray, horizon: int, start: date) -> np.ndarray:
        from statsforecast.models import AutoARIMA  # heavy import, only when this model runs

        result = AutoARIMA(season_length=1).forecast(y=np.array(history, dtype=float), h=horizon)
        return np.clip(np.asarray(result["mean"], dtype=float), 0.0, None)
