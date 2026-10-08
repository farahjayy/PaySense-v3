"""Which forecaster the API serves (plan P4, task C6).

`SERVED_MODEL` is the outcome of the P3 evaluation (reports/engine1/selection.json, ADR D-34):
the global LSTM, run through ONNX Runtime. The benchmarks stay selectable for tests and as a
fallback; changing the served model is a one-line edit plus the ADR that justifies it.
"""

from functools import lru_cache

from app.engines.forecasting.models import MovingAverage, Naive
from app.engines.forecasting.onnx_model import load_served
from app.engines.forecasting.simulate import Forecaster

SERVED_MODEL = "lstm"
ARTEFACT_VERSION = "v1"


@lru_cache(maxsize=1)
def _lstm() -> Forecaster:
    return load_served(ARTEFACT_VERSION)


def served_forecaster(name: str = SERVED_MODEL) -> Forecaster:
    if name == "lstm":
        return _lstm()
    available = {"naive": Naive, "ma4": lambda: MovingAverage(4), "ma13": lambda: MovingAverage(13)}
    if name not in available:
        raise ValueError(f"model {name!r} is not available in the API process")
    return available[name]()
