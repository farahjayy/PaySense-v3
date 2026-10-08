"""Significance tests for the model comparison (plan P3, task B10).

Small-sample forecast comparisons over-reject with the plain Diebold-Mariano test, so the
Harvey-Leybourne-Newbold correction is used. Across many series the per-series MASE values are
compared with a paired Wilcoxon signed-rank test, and across all models with Friedman plus a
Nemenyi post-hoc test (Demsar 2006). p-values over several comparisons are Holm-adjusted, and every
difference is reported with an effect size, because with thousands of series a trivial gap can be
"significant".
"""

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

# Nemenyi critical values q_alpha at alpha = 0.05 for k = 2..10 models (Demsar 2006, table 5).
NEMENYI_Q05 = {
    2: 1.960,
    3: 2.343,
    4: 2.569,
    5: 2.728,
    6: 2.850,
    7: 2.949,
    8: 3.031,
    9: 3.102,
    10: 3.164,
}
BOOTSTRAP_SAMPLES = 2000
CI_LEVEL = 0.95


@dataclass(frozen=True)
class TestResult:
    statistic: float
    p_value: float
    median_difference: float = 0.0


@dataclass(frozen=True)
class FriedmanResult:
    mean_ranks: dict[str, float]
    p_value: float
    critical_difference: float
    significant_pairs: list[tuple[str, str]]


def holm_adjust(p_values: list[float]) -> list[float]:
    """Holm step-down adjustment, returned in the input order."""
    count = len(p_values)
    order = sorted(range(count), key=lambda i: p_values[i])
    adjusted = [0.0] * count
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (count - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted


def dm_hln(loss_a: np.ndarray, loss_b: np.ndarray, horizon: int) -> TestResult:
    """Diebold-Mariano test with the Harvey-Leybourne-Newbold small-sample correction.

    A negative statistic means model A has the lower loss. Two-sided p-value from Student's t with
    n - 1 degrees of freedom.
    """
    d = np.asarray(loss_a, dtype=float) - np.asarray(loss_b, dtype=float)
    n = len(d)
    if n < 3:
        raise ValueError("need at least three loss differences")
    mean = d.mean()
    centred = d - mean
    variance = float(np.sum(centred**2) / n)
    for lag in range(1, horizon):
        variance += 2 * float(np.sum(centred[lag:] * centred[:-lag]) / n)
    if variance <= 0:
        return (
            TestResult(0.0, 1.0, float(np.median(d)))
            if mean == 0
            else TestResult(math.copysign(math.inf, mean), 0.0, float(np.median(d)))
        )
    dm = mean / math.sqrt(variance / n)
    correction = math.sqrt((n + 1 - 2 * horizon + horizon * (horizon - 1) / n) / n)
    statistic = dm * correction
    p_value = float(2 * stats.t.sf(abs(statistic), df=n - 1))
    return TestResult(float(statistic), p_value, float(np.median(d)))


def wilcoxon_paired(a: np.ndarray, b: np.ndarray) -> TestResult:
    """Paired Wilcoxon signed-rank test on per-series scores; negative median means A is lower."""
    diff = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    median = float(np.median(diff))
    if np.all(diff == 0):
        return TestResult(0.0, 1.0, 0.0)
    result = stats.wilcoxon(diff, zero_method="wilcox")
    return TestResult(float(result.statistic), float(result.pvalue), median)


def friedman_nemenyi(scores: np.ndarray, names: list[str]) -> FriedmanResult:
    """`scores[model, series]` (lower is better). Mean ranks, Friedman p, Nemenyi pairs."""
    k, n = scores.shape
    if k < 3:
        raise ValueError("Friedman needs at least three models")
    if k not in NEMENYI_Q05:
        raise ValueError(f"no Nemenyi critical value tabulated for {k} models")
    ranks = np.apply_along_axis(stats.rankdata, 0, scores)
    mean_ranks = ranks.mean(axis=1)
    p_value = float(stats.friedmanchisquare(*scores).pvalue)
    critical = NEMENYI_Q05[k] * math.sqrt(k * (k + 1) / (6 * n))
    pairs = [
        (names[i], names[j])
        for i in range(k)
        for j in range(i + 1, k)
        if abs(mean_ranks[i] - mean_ranks[j]) > critical
    ]
    return FriedmanResult(
        {name: float(r) for name, r in zip(names, mean_ranks, strict=True)},
        p_value,
        critical,
        pairs,
    )


def bootstrap_median_ci(values: np.ndarray, seed: int) -> tuple[float, float]:
    """Percentile bootstrap interval of the median (the effect size reported beside p-values)."""
    rng = np.random.default_rng(seed)
    values = np.asarray(values, dtype=float)
    draws = rng.choice(values, size=(BOOTSTRAP_SAMPLES, len(values)), replace=True)
    medians = np.median(draws, axis=1)
    tail = (1 - CI_LEVEL) / 2
    low, high = np.quantile(medians, [tail, 1 - tail])
    return float(low), float(high)
