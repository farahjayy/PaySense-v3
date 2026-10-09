"""Repeated, stratified, profile-grouped cross-validation with nested tuning (plan P5, D6).

Each profile is one row of the label file and appears twice only inside a training set
(duplicate-and-weight), so a profile can never sit on both sides of a split. Strata are quantile
bins of the soft label (at most ten; ties at exactly 0 or 1 merge some), so every fold sees the
whole range of risk. Tuning happens inside each training fold, never on the fold it is scored on.
Scoring is the Brier score against the soft label, overall and for each subgroup of `Dataset`.
"""

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats
from sklearn.model_selection import StratifiedKFold

from ml.engine2_train.data import Dataset
from ml.engine2_train.metrics import all_metrics, brier
from ml.engine2_train.models import fit_soft, tune

DEFAULT_REPEATS = 5
DEFAULT_FOLDS = 5


@dataclass
class CvResult:
    name: str
    features: tuple[str, ...]
    fold_metrics: list[dict[str, float]] = field(default_factory=list)
    fold_sizes: list[tuple[int, int]] = field(default_factory=list)  # (train, test)
    oof: np.ndarray | None = None  # (repeats, profiles): out-of-fold predictions per repeat
    chosen_params: list[dict[str, Any]] = field(default_factory=list)

    def metric(self, key: str) -> np.ndarray:
        return np.array([m[key] for m in self.fold_metrics])

    def mean(self, key: str) -> float:
        return float(np.nanmean(self.metric(key)))

    def standard_error(self, key: str) -> float:
        values = self.metric(key)
        return float(np.nanstd(values, ddof=1) / math.sqrt(len(values)))


def folds(data: Dataset, repeats: int, k: int, seed: int):
    """Yield (repeat, fold, train_idx, test_idx), stratified on the soft label's quantile bins."""
    strata = data.strata()
    for repeat in range(repeats):
        splitter = StratifiedKFold(n_splits=k, shuffle=True, random_state=seed + repeat)
        for fold, (train, test) in enumerate(splitter.split(data.x, strata)):
            yield repeat, fold, train, test


def cross_validate(
    name: str,
    data: Dataset,
    repeats: int = DEFAULT_REPEATS,
    k: int = DEFAULT_FOLDS,
    trials: int = 12,
    seed: int = 0,
    fixed_params: dict[str, Any] | None = None,
    constrained: bool = True,
) -> CvResult:
    """Nested CV for one candidate. `fixed_params` skips tuning (tests and learning curves only:
    a fixed setting tuned on the same data would leak into the score)."""
    result = CvResult(name, data.names)
    result.oof = np.full((repeats, len(data)), np.nan)
    groups = data.subgroups()
    for repeat, fold, train, test in folds(data, repeats, k, seed):
        if fixed_params is not None:
            params = fixed_params
        elif trials > 0:
            params = tune(
                name, data.x[train], data.y[train], data.names, trials, seed + fold, brier,
                constrained,
            )  # fmt: skip
        else:
            params = {}
        fitted = fit_soft(name, params, data.x[train], data.y[train], data.names, seed, constrained)
        pred = fitted.predict(data.x[test])
        result.oof[repeat, test] = pred
        metrics = all_metrics(pred, data.y[test])
        for group, mask in groups.items():
            inside = mask[test]
            metrics[f"brier@{group}"] = (
                brier(pred[inside], data.y[test][inside]) if inside.any() else math.nan
            )
        result.fold_metrics.append(metrics)
        result.fold_sizes.append((len(train), len(test)))
        result.chosen_params.append(params)
    return result


def nadeau_bengio(a: CvResult, b: CvResult, key: str = "brier") -> tuple[float, float, float]:
    """Corrected resampled t-test of A against B on the per-fold scores.

    The variance is inflated by (1/J + n_test/n_train) because the folds overlap, which the plain
    paired t-test ignores. Returns (mean difference A - B, t statistic, two-sided p). Negative
    means A has the lower (better) score.
    """
    d = a.metric(key) - b.metric(key)
    j = len(d)
    train, test = a.fold_sizes[0]
    variance = float(np.var(d, ddof=1))
    if variance == 0:
        return float(d.mean()), 0.0 if d.mean() == 0 else math.inf, 1.0 if d.mean() == 0 else 0.0
    t = float(d.mean() / math.sqrt((1 / j + test / train) * variance))
    return float(d.mean()), t, float(2 * stats.t.sf(abs(t), df=j - 1))


def nadeau_bengio_interval(
    a: CvResult, b: CvResult, key: str = "brier", level: float = 0.95
) -> tuple[float, float, float]:
    """(mean difference A - B, low, high): the corrected interval, using the t critical value for
    J - 1 degrees of freedom (2.06 for 5x5 folds), not the normal 1.96."""
    d = a.metric(key) - b.metric(key)
    train, test = a.fold_sizes[0]
    half = float(
        stats.t.ppf(0.5 + level / 2, df=len(d) - 1)
        * np.sqrt((1 / len(d) + test / train) * np.var(d, ddof=1))
    )
    return float(d.mean()), float(d.mean() - half), float(d.mean() + half)
