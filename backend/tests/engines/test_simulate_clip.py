"""F1 (engine v3, D-60): the floor at zero applies to a month's total, not to each week."""

from datetime import date

import numpy as np
import pytest

from app.engines.forecasting.flows import MonthFlows
from app.engines.forecasting.series import WeeklySeries
from app.engines.forecasting.simulate import CLIP_MODES, _month_weights, simulate

TODAY = date(2025, 5, 12)  # a Monday: the first forecast day
START_OF_HISTORY = date(2024, 12, 23)  # + 20 weeks = 12 May 2025
MONTHS = ["2025-05", "2025-06", "2025-07", "2025-08"]
END = date(2025, 8, 31)
ALTERNATING = np.array([[-3000.0, 3000.0]])  # one error path: a week under, a week over


class LastValue:
    name = "last-value"

    def forecast(self, history, horizon, start):
        return np.full(horizon, float(history[-1]))


def series(spend_level=1000, income_level=0):
    return WeeklySeries(
        START_OF_HISTORY,
        np.full(20, spend_level, dtype=np.int64),
        np.full(20, income_level, dtype=np.int64),
    )


def flows(income=0):
    return {m: MonthFlows(income, 0, 0) for m in MONTHS}


def run(clip, errors=ALTERNATING, income=100_000, **kwargs):
    return simulate(
        series=series(**kwargs), known=flows(income), forecaster=LastValue(),
        spend_errors=errors, income_errors=np.zeros(0), start=TODAY, end=END, paths=3, seed=4,
        clip=clip,
    )  # fmt: skip


def weekly_draws(level, errors, weeks):
    return level + np.resize(errors[0], weeks)


def test_the_modes_and_the_default_per_week_clip_are_unchanged():
    assert CLIP_MODES == ("week", "month")
    default = simulate(
        series=series(), known=flows(100_000), forecaster=LastValue(), spend_errors=ALTERNATING,
        income_errors=np.zeros(0), start=TODAY, end=END, paths=3, seed=4,
    )  # fmt: skip
    assert default == run("week")


def test_a_monthly_clip_keeps_a_negative_week_inside_a_positive_month():
    per_week, per_month = run("week"), run("month")
    weights = _month_weights(TODAY, per_week.weeks, TODAY, END, MONTHS)
    draws = weekly_draws(1000, ALTERNATING, per_week.weeks)
    assert per_month.monthly_margin_p50_sen == [
        int(round(v)) for v in 100_000 - np.clip(draws @ weights, 0, None)
    ]
    assert per_week.monthly_margin_p50_sen == [
        int(round(v)) for v in 100_000 - np.clip(draws, 0, None) @ weights
    ]
    # the weekly floor deleted the negative weeks, so every month spent more than it did
    assert all(
        m > w
        for m, w in zip(per_month.monthly_margin_p50_sen, per_week.monthly_margin_p50_sen,
                        strict=True)
    )  # fmt: skip


def test_a_negative_month_is_floored_at_zero():
    result = run("month", errors=np.array([[-5000.0]]))
    assert result.monthly_margin_p50_sen == [100_000] * len(MONTHS)
    assert result.p_shortfall == 0.0


def test_the_weekly_feature_summaries_stay_floored_per_week():
    per_week, per_month = run("week"), run("month")
    assert per_month.weekly_spend_p50_sen == per_week.weekly_spend_p50_sen
    assert per_month.weekly_spend_p90_sen == per_week.weekly_spend_p90_sen
    assert per_month.weekly_spend_p50_sen >= 0


def test_monthly_income_is_floored_per_month_too():
    result = simulate(
        series=series(spend_level=0, income_level=1000), known=flows(), forecaster=LastValue(),
        spend_errors=np.zeros(0), income_errors=ALTERNATING, start=TODAY, end=END, paths=3,
        seed=2, clip="month",
    )  # fmt: skip
    weights = _month_weights(TODAY, result.weeks, TODAY, END, MONTHS)
    expected = np.clip(weekly_draws(1000, ALTERNATING, result.weeks) @ weights, 0, None)
    assert result.monthly_income_p10_sen == pytest.approx(float(expected.mean()))


def test_an_unknown_clip_mode_is_refused():
    with pytest.raises(ValueError, match="clip"):
        run("day")
