import math

import numpy as np
import pytest

from ml.engine1_eval.metrics import (
    cumulative_margin_error,
    interval_coverage,
    interval_width,
    mase,
    naive_scale,
    rmsse,
)


def test_the_scale_is_the_mean_absolute_one_step_naive_error():
    assert naive_scale(np.array([1, 3, 2, 5])) == 2.0  # |2| |1| |3|


def test_a_constant_or_single_point_history_has_no_scale():
    assert naive_scale(np.array([4, 4, 4])) is None
    assert naive_scale(np.array([4])) is None


def test_mase_is_the_mean_absolute_error_over_the_scale():
    assert mase(np.array([4, 6]), np.array([5, 5]), scale=2.0) == 0.5


def test_mase_is_undefined_without_a_scale_rather_than_zero():
    assert math.isnan(mase(np.array([4, 6]), np.array([5, 5]), scale=None))


def test_a_forecast_as_good_as_the_naive_history_error_scores_one():
    history = np.array([0.0, 2.0, 4.0, 6.0])  # scale 2
    assert mase(np.array([8.0, 8.0]), np.array([6.0, 10.0]), naive_scale(history)) == 1.0


def test_rmsse_is_the_root_mean_squared_error_over_the_naive_in_sample_rmse():
    history = np.array([0.0, 2.0, 4.0, 6.0])  # naive mse = 4

    assert rmsse(np.array([1.0, 3.0]), np.array([0.0, 0.0]), history) == pytest.approx(
        math.sqrt(5 / 4)
    )


def test_rmsse_is_undefined_for_a_constant_history():
    assert math.isnan(rmsse(np.array([1.0]), np.array([0.0]), np.array([2.0, 2.0, 2.0])))


def test_coverage_is_the_share_of_actuals_inside_the_interval():
    actual = np.array([1, 2, 3, 4])
    lower = np.array([0, 0, 0, 5])
    upper = np.array([2, 2, 2, 6])

    assert interval_coverage(actual, lower, upper) == 0.5
    assert interval_width(lower, upper) == 1.75


def test_cumulative_margin_error_compares_running_income_minus_spend():
    income_actual, income_forecast = np.array([10, 0, 0]), np.array([5, 5, 5])
    spend_actual, spend_forecast = np.array([3, 3, 3]), np.array([4, 4, 4])
    # realised running margin 7, 4, 1; forecast 1, 2, 3

    assert (
        cumulative_margin_error(
            income_actual, income_forecast, spend_actual, spend_forecast, horizon=2
        )
        == 2.0
    )
    assert (
        cumulative_margin_error(
            income_actual, income_forecast, spend_actual, spend_forecast, horizon=3
        )
        == 2.0
    )
    assert (
        cumulative_margin_error(
            income_actual, income_forecast, spend_actual, spend_forecast, horizon=1
        )
        == 6.0
    )


def test_cumulative_margin_error_rejects_a_horizon_longer_than_the_forecast():
    with pytest.raises(ValueError, match="horizon"):
        cumulative_margin_error(np.zeros(2), np.zeros(2), np.zeros(2), np.zeros(2), horizon=3)
