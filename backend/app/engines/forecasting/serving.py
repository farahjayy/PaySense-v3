"""Which forecaster the API serves (plan P4, task C6).

`SERVED_MODEL` records the outcome of the P3 evaluation (reports/engine1/selection.json). Until
that run finishes the 13-week moving average, the strongest benchmark in the early small runs, is
the placeholder; changing it is a one-line edit plus the ADR that justifies it.
"""

from app.engines.forecasting.models import MovingAverage, Naive
from app.engines.forecasting.simulate import Forecaster

SERVED_MODEL = "ma13"


def served_forecaster(name: str = SERVED_MODEL) -> Forecaster:
    available = {"naive": Naive, "ma4": lambda: MovingAverage(4), "ma13": lambda: MovingAverage(13)}
    if name not in available:
        raise ValueError(f"model {name!r} is not available in the API process")
    return available[name]()
