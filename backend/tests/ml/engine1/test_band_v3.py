"""Engine v3 band candidate (R3): groups, population fit, totals, scores and the decision."""

from datetime import date

import numpy as np
import pytest

from app.engines.forecasting.bands import parse_rule
from app.engines.forecasting.models import MovingAverage
from ml.engine1_eval.band_calibration import COHORT, DEV_PROFILES, EVAL_POOL, GRID, dev_profiles
from ml.engine1_eval.band_calibration import test_profiles as heldout_profiles
from ml.engine1_eval.band_fresh_check import fresh_profiles
from ml.engine1_eval.band_v3 import (
    F_PROFILES,
    P_PROFILES,
    POP_LENGTHS,
    Record,
    coverage,
    decide,
    fit_table,
    fresh_v3_profiles,
    median_bias,
    population_paths,
    population_profiles,
    population_windows,
    records_for,
    render,
    student_bootstrap,
    summarise,
    window_totals,
)
from ml.engine1_eval.data import Series
from ml.engine1_eval.outcome_check import outcome_profiles

R2 = parse_rule(
    {
        "version": "2",
        "buckets": [
            {"min_weeks": 17, "spend": 2.0, "income": 1.0},
            {"min_weeks": 26, "spend": 1.5, "income": 1.2},
        ],
    }
)


# --- groups --------------------------------------------------------------------------------------


def test_the_population_and_fresh_groups_are_new_and_disjoint():
    used = (
        set(dev_profiles(DEV_PROFILES))
        | set(fresh_profiles())
        | set(outcome_profiles())
        | set(heldout_profiles())
    )
    population, fresh = population_profiles(), fresh_v3_profiles()
    assert len(set(population)) == P_PROFILES == 300
    assert len(set(fresh)) == F_PROFILES == 500
    assert not set(population) & used and not set(fresh) & used
    assert not set(population) & set(fresh)
    for group in (population, fresh):
        assert all(EVAL_POOL <= i < COHORT and i % 10 != 0 for i in group)
    assert population == population_profiles() and fresh == fresh_v3_profiles()  # seeded


def test_one_seeded_window_per_history_length_inside_the_series():
    windows = population_windows(4001, 78)
    assert [length for _, length in windows] == list(POP_LENGTHS)
    for end, length in windows:
        assert length <= end <= 78 - 13
    assert windows == population_windows(4001, 78)
    assert windows != population_windows(4002, 78)


# --- the population record ---


def _series(kind, values, profile=4001):
    return Series(f"synthetic-{profile}-{kind}", kind, "synthetic", date(2024, 7, 1), values)


def test_population_paths_are_errors_as_a_share_of_the_windows_level():
    values = np.r_[np.full(40, 100.0), np.full(38, 300.0)]  # a level that jumps
    paths = population_paths([_series("spend", values)], MovingAverage(13))
    assert paths["spend"].shape == (len(POP_LENGTHS), 13)
    for (end, length), row in zip(population_windows(4001, 78), paths["spend"], strict=True):
        history = values[end - length : end]
        level = history[-26:].mean()
        forecast = history[-13:].mean()
        np.testing.assert_allclose(row, (values[end : end + 13] - forecast) / level)


def test_a_window_with_no_level_is_left_out():
    paths = population_paths([_series("income", np.zeros(78))], MovingAverage(13))
    assert paths["income"].shape == (0, 13)


# --- totals under each clip ----------------------------------------------------------------------


def test_window_totals_floor_weeks_or_months():
    monday = date(2025, 9, 29)  # the 13 weeks span September, October, November, December
    sims = np.array([[-100.0, 300.0] * 6 + [-100.0]])
    week = window_totals(sims, monday, "week")
    month = window_totals(sims, monday, "month")
    assert week[0] == pytest.approx(300.0 * 6)
    assert month[0] < week[0]
    assert month[0] == pytest.approx(sims.sum(), abs=400.0)  # only a month-end straddle differs


# --- records and scores --------------------------------------------------------------------------


def test_records_score_every_rule_at_every_origin():
    rng = np.random.default_rng(0)
    values = 1000.0 + rng.normal(0, 100, 78)
    pop = {"spend": np.zeros((3, 13)), "income": np.zeros((3, 13))}
    models = {"lstm": MovingAverage(4), "ma13": MovingAverage(13)}
    records = records_for(_series("spend", values), models, R2, {"lstm": pop, "ma13": pop}, rng)
    assert [r.weeks for r in records] == list(range(17, 78 - 13 + 1, 4))
    for r in records:
        assert isinstance(r.inside["R1"], bool) and isinstance(r.inside["R2"], bool)
        assert r.inside["R3"].shape == (len(GRID),) and r.bias["MA13-R3"].shape == (len(GRID),)


def _rec(kind, weeks, profile, inside_r2, inside_r3_at, bias_r2=0.2, bias_r3=0.05):
    grid = np.zeros(len(GRID), dtype=bool)
    grid[[GRID.index(f) for f in inside_r3_at]] = True
    bias = np.full(len(GRID), bias_r3)
    return Record(
        profile, kind, weeks,
        {"R1": inside_r2, "R2": inside_r2, "R3": grid, "MA13-R3": grid},
        {"R1": bias_r2, "R2": bias_r2, "R3": bias, "MA13-R3": bias},
    )  # fmt: skip


def test_the_table_is_the_smallest_factor_reaching_80_percent_per_bucket():
    records = [_rec("spend", 20, i, True, [1.4, 1.5] if i < 8 else [1.5]) for i in range(10)]
    records += [_rec("income", 30, i, True, [2.0] if i < 3 else []) for i in range(10)]
    table = fit_table(records, "R3")
    assert table["spend"][0] == 1.4  # 8 of 10 inside at 1.4: exactly 0.80
    assert table["income"][1] == 2.0  # never reaches 0.80: the best coverage


def test_coverage_and_bias_read_the_fitted_factor():
    records = [_rec("spend", 20, i, i < 5, [1.5]) for i in range(10)]
    table = {"spend": [1.5, 1.0, 1.0, 1.0], "income": [1.0] * 4}
    assert coverage(records, "R3", table) == 1.0
    assert coverage(records, "R2") == 0.5
    assert median_bias(records, "R3", table) == pytest.approx(0.05)
    assert median_bias(records, "R2") == pytest.approx(0.2)


def test_the_bootstrap_resamples_students():
    records = [_rec("spend", 20, i, i % 2 == 0, [1.5]) for i in range(20)]
    table = {"spend": [1.5] * 4, "income": [1.0] * 4}
    ci = student_bootstrap(records, table, "spend", draws=200, seed=1)
    assert ci["coverage_r3_minus_r2"][0] == pytest.approx(0.5)
    low, high = ci["coverage_r3_minus_r2"][1:]
    assert low <= 0.5 <= high


# --- the pre-registered decision -----------------------------------------------------------------


def _fresh(cov2=0.7, cov3=0.78, bias2=0.15, bias3=0.02, cells=None):
    kinds = {
        k: {"R2": {"coverage": cov2, "bias": bias2}, "R3": {"coverage": cov3, "bias": bias3}}
        for k in ("spend", "income")
    }
    return {
        "overall": kinds,
        "cells": cells or {"spend": [(0.4, 0.8), (0.8, 0.8)], "income": [(0.3, 0.8), (0.9, 0.82)]},
    }


OUTCOME_OK = {"13": [-0.002, -0.004, 0.001], "26": [0.001, -0.001, 0.003]}


def test_the_candidate_is_served_only_when_every_criterion_holds():
    assert decide(_fresh(), OUTCOME_OK)["serve"] is True


@pytest.mark.parametrize(
    "fresh, outcome, failing",
    [
        (_fresh(cov3=0.95), OUTCOME_OK, 1),  # overshoots further from 0.80 than R2 was
        (_fresh(bias3=-0.2), OUTCOME_OK, 2),  # a larger bias in the other direction
        (_fresh(cells={"spend": [(0.7, 0.6)], "income": [(0.7, 0.8)]}), OUTCOME_OK, 3),
        (_fresh(), {"13": [0.01, 0.004, 0.02], "26": [0.0, -0.01, 0.01]}, 4),
    ],
)
def test_each_criterion_can_hold_the_candidate_back(fresh, outcome, failing):
    verdict = decide(fresh, outcome)
    assert verdict["serve"] is False
    assert [c["id"] for c in verdict["criteria"] if not c["holds"]] == [failing]


def test_a_cell_falling_from_above_to_nominal_is_not_a_loss():
    cells = {"spend": [(0.95, 0.80)], "income": [(0.9, 0.81)]}
    assert decide(_fresh(cells=cells), OUTCOME_OK)["serve"] is True


def test_the_report_shows_every_rule_and_says_it_is_generated():
    records = [_rec(k, w, i, i % 2 == 0, [1.5]) for k in ("spend", "income") for w in (20, 30)
               for i in range(4)]  # fmt: skip
    table = {"spend": [1.5] * 4, "income": [1.5] * 4}
    verdict = decide(_fresh(), OUTCOME_OK)
    summary = summarise(
        dev=records, fresh=records, tables={"R3": table, "MA13-R3": table}, rule_v2=R2,
        population={"spend": np.zeros((2, 13)), "income": np.zeros((1, 13))},
        ids={"D": [1], "P": [2], "F": [3, 4]}, bootstrap_draws=50,
    )  # fmt: skip
    page = render(summary, verdict, outcome=OUTCOME_OK)
    assert "do not edit by hand" in page
    for name in ("x1.5 (R1)", "served table (R2)", "candidate (R3)", "MA13, R3 (benchmark)"):
        assert name in page
    assert "Decision" in page and "nan" not in page
