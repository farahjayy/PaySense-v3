from datetime import date

import numpy as np
import pytest

from app.engines.forecasting.flows import MonthFlows
from app.engines.forecasting.series import WeeklySeries
from app.engines.forecasting.simulate import (
    band,
    block_bootstrap,
    health_score,
    simulate,
)

TODAY = date(2025, 5, 12)  # a Monday
HISTORY_WEEKS = 20
START_OF_HISTORY = date(2024, 12, 23)  # + 20 weeks = 12 May 2025: the history ends the day before


class LastValue:
    """A fake forecaster: next weeks look like the last observed week."""

    name = "last-value"

    def forecast(self, history, horizon, start):
        return np.full(horizon, float(history[-1]))


def series(spend_level=6000, income_level=0):
    spend = np.full(HISTORY_WEEKS, spend_level, dtype=np.int64)
    income = np.full(HISTORY_WEEKS, income_level, dtype=np.int64)
    return WeeklySeries(START_OF_HISTORY, spend, income)


def flows(months, income=0, bills=0, instalments=0):
    return {m: MonthFlows(income, bills, instalments) for m in months}


MONTHS = ["2025-05", "2025-06", "2025-07", "2025-08"]
END = date(2025, 8, 31)
NOISE = np.random.default_rng(0).normal(0, 3000, 200)  # about RM30 of weekly noise


def run(known, spend_level=6000, errors=NOISE, paths=2000, seed=1):
    return simulate(
        series=series(spend_level),
        known=known,
        forecaster=LastValue(),
        spend_errors=errors,
        income_errors=np.zeros(0),
        start=TODAY,
        end=END,
        paths=paths,
        seed=seed,
    )


def test_bands_follow_the_pre_registered_thresholds():
    assert band(0.0) == "Safe" and band(0.099) == "Safe"
    assert band(0.10) == "Caution" and band(0.299) == "Caution"
    assert band(0.30) == "At Risk" and band(1.0) == "At Risk"


def test_the_health_score_is_the_chance_of_not_falling_short_as_a_percentage():
    assert health_score(0.0) == 100 and health_score(1.0) == 0 and health_score(0.234) == 77


# --- the author's designed cases: RM600 over 3 months, with a RM3,000/month of bills and food ---
# Weekly spend RM60 (about RM260 a month); rent RM300; instalments RM200 a month for 3 months.
def case(income_per_month):
    known = {
        "2025-05": MonthFlows(income_per_month, 30000, 0),
        "2025-06": MonthFlows(income_per_month, 30000, 20000),
        "2025-07": MonthFlows(income_per_month, 30000, 20000),
        "2025-08": MonthFlows(income_per_month, 30000, 20000),
    }
    return run(known)


def test_rm600_over_three_months_is_safe_on_rm2000_a_month():
    result = case(200000)

    assert result.p_shortfall < 0.10 and band(result.p_shortfall) == "Safe"


def test_the_same_purchase_is_at_risk_on_rm500_a_month():
    result = case(50000)

    assert result.p_shortfall >= 0.30 and band(result.p_shortfall) == "At Risk"


def test_with_no_income_at_all_the_purchase_is_at_risk_even_if_there_were_savings():
    result = case(0)

    assert result.p_shortfall >= 0.30


def test_a_cheaper_plan_on_the_same_income_is_never_riskier_than_a_dearer_one():
    cheap = run(flows(MONTHS, income=70000, bills=30000, instalments=5000))
    dear = run(flows(MONTHS, income=70000, bills=30000, instalments=25000))

    assert cheap.p_shortfall <= dear.p_shortfall


def test_the_worst_month_is_where_the_running_total_first_goes_negative_most_often():
    known = {
        "2025-05": MonthFlows(100000, 30000, 0),
        "2025-06": MonthFlows(0, 40000, 0),  # no income and a big bill in June
        "2025-07": MonthFlows(200000, 30000, 0),
        "2025-08": MonthFlows(200000, 30000, 0),
    }

    result = run(known)

    assert result.p_shortfall > 0.9 and result.worst_month == "2025-06"


def test_a_comfortable_user_has_no_worst_month():
    result = run(flows(MONTHS, income=300000, bills=10000))

    assert result.p_shortfall == 0 and result.worst_month is None


def test_stacked_instalments_from_several_providers_add_up():
    one = run(flows(MONTHS, income=60000, bills=20000, instalments=10000))
    three = run(flows(MONTHS, income=60000, bills=20000, instalments=30000))

    assert three.p_shortfall > one.p_shortfall


# --- mechanics ---
def test_the_cumulative_margin_starts_at_zero_and_accumulates():
    result = run(flows(MONTHS, income=100000, bills=30000), errors=np.zeros(50), paths=10)

    monthly = result.monthly_margin_p50_sen
    cumulative = result.cumulative_margin_p50_sen
    assert cumulative[0] == pytest.approx(monthly[0])
    assert cumulative[-1] == pytest.approx(sum(monthly), abs=len(monthly))


def test_percentiles_are_ordered():
    result = run(flows(MONTHS, income=100000, bills=30000))

    for i in range(len(result.months)):
        assert result.cumulative_margin_p10_sen[i] <= result.cumulative_margin_p50_sen[i]
        assert result.cumulative_margin_p50_sen[i] <= result.cumulative_margin_p90_sen[i]


def test_the_same_seed_gives_the_same_answer_and_a_different_seed_a_different_one():
    known = flows(MONTHS, income=45000, bills=30000)

    a, b, c = run(known, seed=3), run(known, seed=3), run(known, seed=4)

    assert a == b
    assert a.cumulative_margin_p10_sen != c.cumulative_margin_p10_sen


def test_money_in_the_result_is_integer_sen():
    result = run(flows(MONTHS, income=100000, bills=30000))

    assert all(isinstance(v, int) for v in result.cumulative_margin_p50_sen)
    assert all(isinstance(v, int) for v in result.monthly_margin_p50_sen)


def test_weeks_are_split_by_days_across_a_month_boundary():
    # a flat RM70 a week = RM10 a day; the horizon is 12 May to 31 May = 20 days = RM200
    result = simulate(
        series=series(7000),
        known=flows(["2025-05"]),
        forecaster=LastValue(),
        spend_errors=np.zeros(10),
        income_errors=np.zeros(0),
        start=TODAY,
        end=date(2025, 5, 31),
        paths=5,
        seed=1,
    )

    assert result.monthly_margin_p50_sen == [-20000]


def test_the_current_week_only_counts_from_today():
    midweek = date(2025, 5, 14)  # a Wednesday: Mon and Tue are already past
    result = simulate(
        series=series(7000),
        known=flows(["2025-05"]),
        forecaster=LastValue(),
        spend_errors=np.zeros(10),
        income_errors=np.zeros(0),
        start=midweek,
        end=date(2025, 5, 31),
        paths=5,
        seed=1,
    )

    assert result.monthly_margin_p50_sen == [-18 * 1000]  # 18 remaining days at RM10


def test_a_negative_simulated_week_is_floored_at_zero():
    wild = np.full(50, -1_000_000.0)  # errors far larger than the forecast

    result = run(flows(MONTHS, income=100000), errors=wild, paths=10)

    assert result.p_shortfall == 0  # spending cannot go below zero, so margin is just income


def test_block_bootstrap_keeps_runs_of_consecutive_residuals_together():
    residuals = np.arange(100, dtype=float)
    draws = block_bootstrap(residuals, length=12, paths=50, block=4, rng=np.random.default_rng(1))

    assert draws.shape == (50, 12)
    steps = np.diff(draws, axis=1)
    assert np.mean(steps == 1) > 0.6  # most neighbours come from the same block


def test_with_too_few_residuals_it_falls_back_to_plain_resampling():
    draws = block_bootstrap(
        np.array([1.0, 2.0, 3.0]), length=10, paths=5, block=4, rng=np.random.default_rng(1)
    )

    assert draws.shape == (5, 10) and set(np.unique(draws)) <= {1.0, 2.0, 3.0}


def test_no_residuals_at_all_means_no_noise():
    draws = block_bootstrap(np.zeros(0), length=6, paths=3, block=4, rng=np.random.default_rng(1))

    assert not draws.any()


def test_the_horizon_is_capped_at_fifty_two_weeks():
    result = simulate(
        series=series(7000),
        known=flows(
            [f"2025-{m:02d}" for m in range(5, 13)] + [f"2026-{m:02d}" for m in range(1, 9)]
        ),
        forecaster=LastValue(),
        spend_errors=np.zeros(10),
        income_errors=np.zeros(0),
        start=TODAY,
        end=date(2026, 8, 31),
        paths=5,
        seed=1,
    )

    assert result.horizon_capped and result.weeks == 52


def test_what_already_happened_this_month_counts_toward_this_months_margin():
    base = dict(
        series=series(7000), known=flows(["2025-05"]), forecaster=LastValue(),
        spend_errors=np.zeros(10), income_errors=np.zeros(0), start=TODAY,
        end=date(2025, 5, 31), paths=5, seed=1,
    )  # fmt: skip

    without = simulate(**base)
    earned = simulate(**base, month_to_date_sen=50000)

    assert earned.monthly_margin_p50_sen[0] == without.monthly_margin_p50_sen[0] + 50000
    assert earned.p_shortfall <= without.p_shortfall


def test_the_horizon_runs_to_the_end_of_its_last_month():
    mid = simulate(
        series=series(7000), known=flows(["2025-05", "2025-06"]), forecaster=LastValue(),
        spend_errors=np.zeros(10), income_errors=np.zeros(0), start=TODAY,
        end=date(2025, 6, 10), paths=5, seed=1,
    )  # fmt: skip
    whole = simulate(
        series=series(7000), known=flows(["2025-05", "2025-06"]), forecaster=LastValue(),
        spend_errors=np.zeros(10), income_errors=np.zeros(0), start=TODAY,
        end=date(2025, 6, 30), paths=5, seed=1,
    )  # fmt: skip

    assert mid.monthly_margin_p50_sen == whole.monthly_margin_p50_sen


def test_whole_error_paths_are_joined_so_a_wrong_level_stays_wrong():
    from app.engines.forecasting.simulate import path_bootstrap

    paths = np.array([[10.0] * 8, [-10.0] * 8])  # the model was either high all the time or low

    draws = path_bootstrap(paths, length=16, paths=200, rng=np.random.default_rng(1))

    assert draws.shape == (200, 16)
    for row in draws:
        assert len(set(row[:8])) == 1 and len(set(row[8:])) == 1  # constant within a piece


def test_path_resampling_gives_bands_of_the_right_order_for_a_drifting_level():
    from app.engines.forecasting.errors import rolling_error_paths, widen
    from app.engines.forecasting.models import MovingAverage
    from app.engines.forecasting.service import ERROR_INFLATION
    from app.engines.forecasting.simulate import path_bootstrap

    def ar1(seed, n, phi=0.5, sd=1000.0):
        rng = np.random.default_rng(seed)
        x, out = 0.0, []
        for _ in range(n):
            x = phi * x + rng.normal(0, sd)
            out.append(10000 + x)
        return np.array(out)

    truth, spread, covered = [], [], []
    for seed in range(120):
        full = ar1(seed, 40 + 13)
        history, future = full[:40], full[40:]
        point = MovingAverage(8).forecast(history, 13, TODAY)
        errors = widen(rolling_error_paths(history, TODAY, MovingAverage(8)), ERROR_INFLATION)
        sums = path_bootstrap(errors, 13, 200, np.random.default_rng(seed)).sum(axis=1)
        actual = float(future.sum() - point.sum())
        truth.append(actual)
        spread.append(sums.std())
        low, high = np.percentile(sums, [10, 90])
        covered.append(low <= actual <= high)

    # Measured in the P4 calibration run: about 0.8 coverage at 40 weeks of history for this
    # series. It is lower for shorter or more persistent series; the serving report says so.
    assert 0.7 < np.mean(spread) / np.std(truth) < 2.0
    assert np.mean(covered) >= 0.6
