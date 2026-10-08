"""Prophet, one of the three literature candidates (D-05)."""

import logging
from datetime import date

import numpy as np

YEARLY_SEASONALITY_MIN_WEEKS = 104  # two years: fewer cannot identify a yearly cycle
DAYS_PER_WEEK = 7


class ProphetModel:
    """Prophet on the weekly series: a piecewise trend, yearly seasonality only when the history
    spans two years, no weekly or daily seasonality (the data is already weekly), no holidays and
    no tuning on test origins. Forecasts are floored at zero."""

    name = "prophet"

    def forecast(self, history: np.ndarray, horizon: int, start: date) -> np.ndarray:
        import pandas as pd
        from prophet import Prophet  # heavy import, only when this model runs

        logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
        logging.getLogger("prophet").setLevel(logging.WARNING)
        frame = pd.DataFrame(
            {
                "ds": pd.date_range(start, periods=len(history), freq=f"{DAYS_PER_WEEK}D"),
                "y": np.asarray(history, dtype=float),
            }
        )
        model = Prophet(
            yearly_seasonality=len(history) >= YEARLY_SEASONALITY_MIN_WEEKS,
            weekly_seasonality=False,
            daily_seasonality=False,
            uncertainty_samples=0,
        )
        model.fit(frame)
        future = model.make_future_dataframe(
            periods=horizon, freq=f"{DAYS_PER_WEEK}D", include_history=False
        )
        return np.clip(model.predict(future)["yhat"].to_numpy(dtype=float), 0.0, None)
