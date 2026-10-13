"""Exporting each candidate family to ONNX: the served numbers must be the trained model's."""

import numpy as np
import pytest

from app.engines.risk.features import FEATURE_NAMES
from ml.engine2_train.export import (
    ExportError,
    convert,
    parity,
    reference_student,
    within_tolerance,
)
from ml.engine2_train.models import CANDIDATES, fit_soft

N = len(FEATURE_NAMES)


@pytest.fixture(scope="module")
def data():
    rng = np.random.default_rng(3)
    x = rng.normal(size=(600, N))
    signal = 1.2 * x[:, 4] * -1 + 0.8 * x[:, 6] + 0.5 * x[:, 13]
    y = 1 / (1 + np.exp(-signal))  # a soft label in (0, 1)
    return x, y


@pytest.mark.parametrize("family", CANDIDATES)
def test_the_onnx_model_matches_the_trained_model_for_every_family(data, family):
    x, y = data
    fitted = fit_soft(family, {"n_estimators": 60}, x, y, FEATURE_NAMES)

    report = parity(fitted, convert(fitted, N), x[:200])

    assert report["rows"] == 200
    assert report["max_abs_diff"] < 1e-3
    assert report["rows_over_1e-6"] <= 3  # float32 rounding at a split, at most a handful of rows


def test_an_unknown_family_is_not_converted_silently(data):
    x, y = data
    fitted = fit_soft("logistic", {}, x, y, FEATURE_NAMES)
    fitted.name = "mystery"
    # anything that is not one of the tree libraries goes through the scikit-learn converter and
    # fails loudly if the model is not one it knows
    fitted.model = object()
    with pytest.raises(Exception) as caught:  # noqa: B017, PT011 - the converter's error varies
        convert(fitted, N)
    assert caught.type is not AssertionError


def test_a_nan_difference_fails_the_parity_gate_instead_of_slipping_through():
    assert within_tolerance(np.array([0.0, 1e-4]))
    assert not within_tolerance(np.array([0.0, np.nan]))
    assert not within_tolerance(np.array([0.5]))
    assert not within_tolerance(np.array([np.inf]))


class _Dev:
    def __init__(self, y, x):
        self.y, self.x = np.asarray(y), np.asarray(x)


def test_the_reference_student_is_the_median_of_the_safe_profiles_only():
    n = 120
    x = np.vstack([np.full((n, N), 1.0), np.full((n, N), 9.0)])
    y = np.r_[np.full(n, 0.01), np.full(n, 0.6)]
    reference, count = reference_student(_Dev(y, x))
    assert count == n
    assert set(reference) == set(FEATURE_NAMES)
    assert all(value == 1.0 for value in reference.values())


def test_too_few_safe_profiles_is_a_refusal_not_a_guess():
    x, y = np.ones((50, N)), np.full(50, 0.01)
    with pytest.raises(ExportError, match="too few Safe"):
        reference_student(_Dev(y, x))
