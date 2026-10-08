from datetime import date

import numpy as np
import pytest

from ml.engine1_eval.data import Series
from ml.engine1_eval.harness import (
    EvalConfig,
    evaluate_pair,
    evaluate_series,
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

        def forecast(self, history, horizon):
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

        def forecast(self, history, horizon):
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
