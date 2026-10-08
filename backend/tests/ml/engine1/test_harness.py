from datetime import date, timedelta

import numpy as np
import pytest

from ml.engine1_eval.data import Series
from ml.engine1_eval.harness import (
    EvalConfig,
    evaluate_pair,
    evaluate_series,
    margin_rows,
    rolling_origins,
)
from ml.engine1_eval.models.benchmarks import MovingAverage, Naive

START = date(2025, 1, 6)


def series(values, kind="spend", series_id="s"):
    return Series(series_id, kind, "test", START, np.asarray(values, dtype=float))


CONFIG = EvalConfig(horizon=4, report_horizons=(1, 4), min_train=6, stride=2, min_interval_errors=3)


def test_origins_start_at_the_minimum_history_and_leave_room_for_the_horizon():
    assert rolling_origins(50, min_train=26, horizon=13, stride=4) == [26, 30, 34]


def test_limiting_origins_keeps_the_latest_ones():
    assert rolling_origins(50, 26, 13, 4, max_origins=2) == [30, 34]


def test_a_series_too_short_for_one_origin_has_none():
    assert rolling_origins(20, min_train=26, horizon=13, stride=4) == []


def test_a_model_is_only_ever_shown_history_before_the_origin():
    seen = []

    class Recorder:
        name = "recorder"

        def forecast(self, history, horizon, start):
            seen.append(history.copy())
            assert not history.flags.writeable  # cannot be altered, and cannot be extended
            return np.zeros(horizon)

    values = np.arange(1.0, 21.0)
    evaluate_series(series(values), Recorder(), CONFIG)

    origins = rolling_origins(20, 6, 4, 2)
    assert [len(h) for h in seen] == origins
    for history, origin in zip(seen, origins, strict=True):
        assert np.array_equal(history, values[:origin])


def test_an_oracle_that_reads_the_future_scores_nearly_zero_so_the_harness_would_notice():
    values = np.random.default_rng(1).uniform(10, 20, 40)

    class Oracle:
        name = "oracle"

        def forecast(self, history, horizon, start):
            start = len(history)
            return values[start : start + horizon]

    result = evaluate_series(series(values), Oracle(), CONFIG)

    assert result.rows and all(r["mase_4"] == pytest.approx(0, abs=1e-9) for r in result.rows)


def test_naive_mase_matches_a_hand_calculation():
    values = [1, 3, 2, 5, 4, 6, 8, 7, 9, 10]  # history of 6 at the first origin
    config = EvalConfig(horizon=2, report_horizons=(1, 2), min_train=6, stride=100)

    result = evaluate_series(series(values), Naive(), config)

    # history 1,3,2,5,4,6 -> scale (2+1+3+1+2)/5 = 1.8; naive forecast 6,6; actual 8,7
    # mae = (2 + 1) / 2 = 1.5; mase = 1.5 / 1.8
    (row,) = result.rows
    assert row["origin"] == 6
    assert row["mase_2"] == pytest.approx(1.5 / 1.8)
    assert row["mase_1"] == pytest.approx(2 / 1.8)


def test_origins_with_a_constant_history_are_skipped_and_counted_not_scored_as_zero():
    result = evaluate_series(series([5.0] * 20), Naive(), CONFIG)

    assert result.rows == []
    assert result.skipped == len(rolling_origins(20, 6, 4, 2))


def test_intervals_appear_only_once_enough_earlier_errors_exist():
    values = np.random.default_rng(2).uniform(5, 15, 60)
    result = evaluate_series(series(values), MovingAverage(3), CONFIG)

    coverage = [r["coverage_4"] for r in result.rows]
    assert np.isnan(coverage[0])
    assert not np.isnan(coverage[-1])
    assert 0 <= coverage[-1] <= 1


def test_interval_errors_never_come_from_the_future_of_the_origin():
    """A series that is wild only in its last stretch must not widen earlier intervals."""
    calm = np.random.default_rng(3).normal(10, 0.1, 40)
    wild = np.concatenate([calm[:30], np.random.default_rng(4).normal(10, 50, 10)])

    a = evaluate_series(series(calm), MovingAverage(3), CONFIG).rows
    b = evaluate_series(series(wild), MovingAverage(3), CONFIG).rows

    early = [(x["width_4"], y["width_4"]) for x, y in zip(a, b, strict=True) if x["origin"] <= 20]
    assert len(early) >= 4
    np.testing.assert_allclose([w[0] for w in early], [w[1] for w in early])  # NaN == NaN here


def test_the_pair_evaluation_reports_cumulative_margin_error_per_horizon():
    income = series(np.tile([10.0, 0.0, 0.0, 0.0], 10), kind="income")
    spend = series(np.tile([3.0, 3.0, 4.0, 2.0], 10))

    rows = evaluate_pair(spend, income, Naive(), CONFIG)

    assert rows and {"margin_1", "margin_4"} <= set(rows[0])
    assert all(r["margin_4"] >= 0 for r in rows)


def test_two_runs_give_identical_rows():
    values = np.random.default_rng(5).uniform(1, 9, 50)

    first = evaluate_series(series(values), MovingAverage(3), CONFIG).rows
    second = evaluate_series(series(values), MovingAverage(3), CONFIG).rows

    np.testing.assert_equal(first, second)


def test_a_first_origin_date_keeps_every_origin_in_the_later_part_of_the_calendar():
    config = EvalConfig(
        horizon=4,
        report_horizons=(1, 4),
        min_train=6,
        stride=2,
        first_origin_date=date(2025, 3, 3),  # 8 weeks after the series starts
    )

    rows = evaluate_series(series(np.arange(1.0, 40.0)), Naive(), config).rows

    assert min(r["origin"] for r in rows) == 8


def test_a_history_limit_shows_the_model_only_the_most_recent_weeks():
    seen = []

    class Recorder:
        name = "recorder"

        def forecast(self, history, horizon, start):
            seen.append((len(history), start))
            return np.zeros(horizon)

    config = EvalConfig(horizon=4, report_horizons=(4,), min_train=10, stride=100, history_limit=6)
    evaluate_series(series(np.arange(1.0, 30.0)), Recorder(), config)

    assert seen == [(6, date(2025, 1, 6) + timedelta(weeks=4))]


def test_a_mid_week_cutoff_rounds_up_so_no_origin_precedes_it():
    config = EvalConfig(
        horizon=4,
        report_horizons=(1, 4),
        min_train=2,
        stride=1,
        first_origin_date=date(2025, 3, 3) + timedelta(days=3),  # a Thursday, 8 weeks and 3 days in
    )

    rows = evaluate_series(series(np.arange(1.0, 40.0)), Naive(), config).rows

    # week 8 starts on 3 March, before the cutoff; the first whole week at or after it is week 9
    assert min(r["origin"] for r in rows) == 9


def test_a_non_finite_forecast_is_an_error_not_a_scored_nan():
    class Broken:
        name = "broken"

        def forecast(self, history, horizon, start):
            return np.full(horizon, np.nan)

    with pytest.raises(ValueError, match="non-finite"):
        evaluate_series(series(np.arange(1.0, 40.0)), Broken(), CONFIG)


def test_errors_are_scaled_by_the_whole_history_whatever_the_model_is_shown():
    values = np.concatenate([np.random.default_rng(6).uniform(0, 100, 30), np.full(30, 5.0)])
    full = EvalConfig(horizon=4, report_horizons=(4,), min_train=40, stride=100)
    short = EvalConfig(horizon=4, report_horizons=(4,), min_train=40, stride=100, history_limit=10)

    a = evaluate_series(series(values), Naive(), full).rows[0]
    b = evaluate_series(series(values), Naive(), short).rows[0]

    assert a["scale"] == pytest.approx(b["scale"])  # a 10-week view does not rescale the error
    assert b["train_len"] == 10 and a["train_len"] == 40


def test_the_signed_bias_is_positive_for_a_model_that_over_forecasts():
    class High:
        name = "high"

        def forecast(self, history, horizon, start):
            return np.full(horizon, 1000.0)

    row = evaluate_series(series(np.random.default_rng(7).uniform(1, 10, 40)), High(), CONFIG).rows[
        0
    ]

    assert row["bias_4"] > 0


def test_margin_rows_reuse_stored_forecasts_instead_of_refitting():
    calls = []

    class Counting:
        name = "counting"

        def forecast(self, history, horizon, start):
            calls.append(len(history))
            return np.full(horizon, 5.0)

    spend, income = series(np.tile([3.0, 4.0], 20)), series(np.tile([10.0, 0.0], 20), kind="income")
    s_eval = evaluate_series(spend, Counting(), CONFIG)
    i_eval = evaluate_series(income, Counting(), CONFIG)
    fits = len(calls)

    rows = margin_rows(spend, income, s_eval, i_eval, "counting", CONFIG)

    assert len(calls) == fits and rows
