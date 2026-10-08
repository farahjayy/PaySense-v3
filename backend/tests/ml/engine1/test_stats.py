import math

import numpy as np
import pytest

from ml.engine1_eval.stats import (
    bootstrap_median_ci,
    dm_hln,
    friedman_nemenyi,
    holm_adjust,
    wilcoxon_paired,
)


def test_holm_adjustment_matches_a_hand_calculation_and_keeps_the_order():
    # sorted 0.01, 0.03, 0.04 -> x3, x2, x1 = 0.03, 0.06, 0.04 -> made monotone 0.03, 0.06, 0.06
    assert holm_adjust([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_holm_never_exceeds_one():
    assert holm_adjust([0.9, 0.8]) == pytest.approx([1.0, 1.0])


def test_dm_hln_finds_no_difference_between_identical_losses():
    losses = np.random.default_rng(1).uniform(0, 1, 40)

    result = dm_hln(losses, losses.copy(), horizon=1)

    assert result.statistic == 0 and result.p_value == 1.0


def test_dm_hln_detects_a_consistently_better_model_and_gets_the_sign_right():
    rng = np.random.default_rng(2)
    worse = rng.uniform(1, 2, 60)
    better = worse - rng.uniform(0.3, 0.5, 60)

    forward = dm_hln(better, worse, horizon=1)
    backward = dm_hln(worse, better, horizon=1)

    assert forward.p_value < 0.001
    assert forward.statistic < 0 < backward.statistic  # negative: the first model has less loss
    assert forward.statistic == pytest.approx(-backward.statistic)


def test_the_hln_correction_is_applied():
    d = np.array([1.0, 2.0, 0.5, 1.5, 1.0, 2.5, 0.0, 1.0])
    n = len(d)
    raw = d.mean() / math.sqrt(d.var(ddof=0) / n)  # horizon 1: only the zero-lag variance
    corrected = raw * math.sqrt((n + 1 - 2 + 0) / n)  # HLN factor for h = 1

    result = dm_hln(d, np.zeros(n), horizon=1)

    assert result.statistic == pytest.approx(corrected)


def test_wilcoxon_reports_the_median_difference_and_a_small_p_for_a_clear_gap():
    rng = np.random.default_rng(3)
    a = rng.uniform(0.8, 1.0, 80)
    b = a + rng.uniform(0.05, 0.15, 80)

    result = wilcoxon_paired(a, b)

    assert result.p_value < 1e-6
    assert result.median_difference == pytest.approx(np.median(a - b))
    assert result.median_difference < 0


def test_wilcoxon_with_identical_inputs_has_no_difference_and_p_of_one():
    a = np.array([1.0, 2.0, 3.0])

    result = wilcoxon_paired(a, a.copy())

    assert result.p_value == 1.0 and result.median_difference == 0


def test_friedman_nemenyi_ranks_and_critical_difference_match_the_formula():
    # three models, ten series, the models always rank 1, 2, 3 (lower is better)
    scores = np.array([[1.0] * 10, [2.0] * 10, [3.0] * 10])

    result = friedman_nemenyi(scores, ["a", "b", "c"])

    assert result.mean_ranks == {"a": 1.0, "b": 2.0, "c": 3.0}
    assert result.critical_difference == pytest.approx(2.343 * math.sqrt(3 * 4 / (6 * 10)))
    assert result.p_value < 0.001
    assert ("a", "c") in result.significant_pairs and ("a", "b") not in result.significant_pairs


def test_friedman_needs_at_least_three_models():
    with pytest.raises(ValueError, match="three"):
        friedman_nemenyi(np.ones((2, 5)), ["a", "b"])


def test_bootstrap_ci_brackets_the_sample_median_and_is_reproducible():
    diffs = np.random.default_rng(4).normal(0.2, 0.5, 200)

    low, high = bootstrap_median_ci(diffs, seed=1)

    assert low < np.median(diffs) < high
    assert bootstrap_median_ci(diffs, seed=1) == (low, high)


def test_dm_hln_with_overlapping_windows_never_reports_perfect_separation_by_accident():
    """A rectangular lag window can return a non-positive variance for noisy, autocorrelated gaps;
    Bartlett weights keep it positive, so a noisy comparison does not become p = 0."""
    infinite = 0
    for seed in range(100):
        e = np.random.default_rng(seed).normal(size=31)
        d = e[1:] - 0.9 * e[:-1] + 0.1
        outcome = dm_hln(d, np.zeros(30), horizon=13)
        infinite += math.isinf(outcome.statistic)
    assert infinite == 0
