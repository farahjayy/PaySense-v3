import json
from datetime import date

import numpy as np
import pytest

from app.engines.forecasting.onnx_model import MODEL_DIR, OnnxLstm, ServedLstm, load_served
from app.engines.forecasting.serving import SERVED_MODEL, served_forecaster
from app.engines.forecasting.simulate import forecaster_for

START = date(2025, 1, 6)
ARTEFACT = MODEL_DIR / "v1"


@pytest.fixture(scope="module")
def served() -> ServedLstm:
    return load_served("v1")


def history(n=40, level=8000.0, seed=0):
    return level + np.random.default_rng(seed).normal(0, 1500, n).clip(-level, None)


def test_the_artefact_describes_itself_and_matches_the_evaluated_recipe():
    meta = json.loads((ARTEFACT / "metadata.json").read_text(encoding="utf-8"))

    assert meta["model"] == "global-lstm" and meta["kinds"] == ["spend", "income"]
    assert (meta["window"], meta["horizon"], meta["hidden"]) == (26, 13, 32)
    assert meta["training"]["config"] == "full" and meta["selection_sha256"]
    for kind in meta["kinds"]:
        assert meta["parity_with_torch"][kind]["max_abs_difference"] < 1e-4


def test_the_served_model_is_the_lstm_chosen_by_the_evaluation():
    assert SERVED_MODEL == "lstm"
    assert served_forecaster().name == "lstm"


def test_each_kind_has_its_own_network_and_a_bare_call_is_refused(served):
    assert served.for_kind("spend") is not served.for_kind("income")
    with pytest.raises(TypeError, match="per kind"):
        served.forecast(history(), 4, START)


def test_forecasts_are_the_right_length_finite_and_never_negative(served):
    for kind in ("spend", "income"):
        forecast = served.for_kind(kind).forecast(history(), 13, START)

        assert forecast.shape == (13,) and np.all(np.isfinite(forecast)) and np.all(forecast >= 0)


def test_a_forecast_is_in_the_scale_of_the_history(served):
    forecast = served.for_kind("spend").forecast(history(level=8000.0), 13, START)

    assert 2000 < forecast.mean() < 20000  # it forecasts around RM80 a week, not RM8 or RM8,000


def test_the_forecast_scales_with_the_history(served):
    small = served.for_kind("spend").forecast(history(level=1000.0), 13, START)
    large = served.for_kind("spend").forecast(history(level=1000.0) * 10, 13, START)

    assert np.allclose(large, small * 10, rtol=1e-4)


def test_beyond_the_trained_horizon_the_forecast_continues_recursively(served):
    model = served.for_kind("spend")

    long = model.forecast(history(), 40, START)

    assert long.shape == (40,) and np.all(np.isfinite(long))
    assert np.array_equal(long[:13], model.forecast(history(), 13, START))  # same first block


def test_a_short_history_is_padded_and_an_all_zero_one_forecasts_zero(served):
    model = served.for_kind("income")

    assert model.forecast(np.array([5000.0, 7000.0]), 5, START).shape == (5,)
    assert list(model.forecast(np.zeros(30), 5, START)) == [0.0] * 5


def test_an_empty_history_is_an_error(served):
    with pytest.raises(ValueError, match="at least one week"):
        served.for_kind("spend").forecast(np.array([]), 4, START)


def test_the_forecaster_chooser_gives_the_per_kind_model_or_the_same_one(served):
    assert forecaster_for(served, "income") is served.for_kind("income")

    class Plain:
        name = "plain"

    assert forecaster_for(Plain(), "spend").name == "plain"


def test_the_same_input_always_gives_the_same_forecast(served):
    model = served.for_kind("spend")

    assert np.array_equal(
        model.forecast(history(), 13, START), model.forecast(history(), 13, START)
    )


def test_onnx_lstm_can_be_built_directly_from_a_file():
    meta = json.loads((ARTEFACT / "metadata.json").read_text(encoding="utf-8"))

    model = OnnxLstm(ARTEFACT / "lstm_spend.onnx", meta["window"], meta["horizon"], meta["epsilon"])

    assert model.forecast(history(), 4, START).shape == (4,)


def test_the_api_process_never_needs_torch():
    from pathlib import Path

    import app

    root = Path(app.__file__).parent
    offenders = [
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if any(
            line.strip().startswith(("import torch", "from torch"))
            for line in p.read_text(encoding="utf-8").splitlines()
        )
    ]
    assert offenders == []
