from datetime import date, timedelta

import numpy as np
import pytest
import torch

from ml.engine1_eval.data import Series
from ml.engine1_eval.models.arima import AutoArima
from ml.engine1_eval.models.benchmarks import MovingAverage, Naive
from ml.engine1_eval.models.lstm import GlobalLstm, LstmConfig, build_windows
from ml.engine1_eval.models.prophet_model import ProphetModel

START = date(2024, 1, 1)


def ar1(n, seed, level=100.0, phi=0.6, noise=10.0):
    rng = np.random.default_rng(seed)
    values, x = [], 0.0
    for _ in range(n):
        x = phi * x + rng.normal(0, noise)
        values.append(max(level + x, 0.0))
    return np.array(values)


def test_naive_repeats_the_last_week_and_moving_average_the_recent_mean():
    history = np.array([1.0, 2.0, 3.0, 10.0])

    assert list(Naive().forecast(history, 3, START)) == [10.0, 10.0, 10.0]
    assert list(MovingAverage(2).forecast(history, 2, START)) == [6.5, 6.5]
    assert MovingAverage(4).name == "ma4"


def test_a_moving_average_needs_a_positive_window():
    with pytest.raises(ValueError, match="window"):
        MovingAverage(0)


def test_arima_forecasts_a_stable_series_close_to_its_level():
    forecast = AutoArima().forecast(ar1(60, 1), 8, START)

    assert forecast.shape == (8,) and np.all(np.isfinite(forecast)) and np.all(forecast >= 0)
    assert forecast.mean() == pytest.approx(100, abs=15)


def test_arima_copes_with_a_constant_history_and_never_goes_negative():
    forecast = AutoArima().forecast(np.full(30, 50.0), 5, START)
    trending_down = AutoArima().forecast(np.linspace(100, 1, 30), 13, START)

    assert np.all(np.isfinite(forecast))
    assert np.all(trending_down >= 0)


def test_prophet_follows_a_clear_upward_trend():
    history = np.linspace(100, 200, 52) + np.random.default_rng(1).normal(0, 2, 52)

    forecast = ProphetModel().forecast(history, 8, START)

    assert forecast.shape == (8,) and np.all(forecast >= 0)
    assert forecast.mean() > history[-10:].mean()


def make_cohort(count=40, weeks=80, seed=0):
    return [
        Series(f"s{i}", "spend", "test", START, ar1(weeks, seed + i, level=50 + 5 * (i % 7)))
        for i in range(count)
    ]


FAST = LstmConfig(window=12, horizon=4, hidden=8, epochs=3, batch_size=64, window_stride=3)


def test_training_windows_end_before_the_cutoff_date():
    series = make_cohort(count=3, weeks=60)
    cutoff = START + timedelta(weeks=30)

    x, y = build_windows(series, FAST, until=cutoff)
    all_x, _ = build_windows(series, FAST, until=None)

    assert 0 < len(x) < len(all_x)
    # the last usable window's target ends at week 30 (exclusive): context end + horizon <= 30
    limit_windows = sum(
        len(range(FAST.window, 30 - FAST.horizon + 1, FAST.window_stride)) for _ in series
    )
    assert len(x) == limit_windows


def test_windows_are_scaled_by_their_own_mean():
    x, _ = build_windows(make_cohort(count=2), FAST, until=None)

    assert np.allclose(x.mean(axis=1), 1.0, atol=1e-5)


def test_the_lstm_forecasts_the_right_shape_and_never_negative():
    model = GlobalLstm.train(make_cohort(), FAST)

    forecast = model.forecast(ar1(40, 99), 4, START)

    assert forecast.shape == (4,) and np.all(np.isfinite(forecast)) and np.all(forecast >= 0)
    assert model.parameter_count > 0


def test_the_lstm_handles_a_history_shorter_than_its_window_and_an_all_zero_one():
    model = GlobalLstm.train(make_cohort(), FAST)

    assert model.forecast(np.array([50.0, 60.0, 55.0]), 4, START).shape == (4,)
    assert list(model.forecast(np.zeros(20), 4, START)) == [0.0] * 4


def test_the_lstm_refuses_a_horizon_it_was_not_trained_for():
    model = GlobalLstm.train(make_cohort(), FAST)

    with pytest.raises(ValueError, match="horizon|trained"):
        model.forecast(ar1(30, 1), 9, START)


def test_training_twice_with_the_same_seed_gives_identical_weights():
    a = GlobalLstm.train(make_cohort(), FAST).state()
    b = GlobalLstm.train(make_cohort(), FAST).state()

    assert a.keys() == b.keys()
    for key in a:
        assert torch.equal(a[key], b[key]), key


def test_training_with_no_usable_window_is_an_error_not_a_silent_untrained_model():
    short = [Series("a", "spend", "test", START, np.arange(1.0, 10.0))]

    with pytest.raises(ValueError, match="no training windows"):
        GlobalLstm.train(short, FAST)


def test_without_validation_windows_the_lstm_still_trains_every_epoch():
    one_series = make_cohort(count=1, weeks=80)
    config = LstmConfig(window=12, horizon=4, hidden=8, epochs=4, batch_size=64, window_stride=3)

    trained = GlobalLstm.train(one_series, config).state()
    untrained_like = GlobalLstm.train(
        one_series, LstmConfig(**{**config.__dict__, "epochs": 1})
    ).state()

    assert any(not torch.equal(trained[k], untrained_like[k]) for k in trained)


def test_a_mid_week_cutoff_rounds_up_for_training_windows_too():
    series = make_cohort(count=1, weeks=60)
    mid_week = START + timedelta(weeks=30, days=3)  # whole weeks strictly before it: 31

    x, _ = build_windows(series, FAST, until=mid_week)
    exact, _ = build_windows(series, FAST, until=START + timedelta(weeks=30))

    assert len(x) >= len(exact)
    limit = 31
    assert len(x) == len(range(FAST.window, limit - FAST.horizon + 1, FAST.window_stride))
