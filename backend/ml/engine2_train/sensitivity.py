"""Sensitivity runs that sit beside the main comparison (plan P5, D7; audit M3).

* learning curve: does the error of the winner still fall as training profiles are added?
  (ASSUMED 3: is 10,000 profiles enough?)
* monotone constraints: what does constraining the winner cost, against the same model free?
* shortfall definition: how do the labels and the model change if "short" meant any single month
  below RM0 rather than the running total below RM0 (ASSUMED 4)?
"""

from typing import Any

import numpy as np
from sklearn.model_selection import StratifiedKFold

from ml.engine2_train.cv import CvResult, cross_validate, nadeau_bengio, nadeau_bengio_interval
from ml.engine2_train.data import Dataset
from ml.engine2_train.metrics import band_agreement, brier
from ml.engine2_train.models import fit_soft

FRACTIONS = (0.2, 0.4, 0.6, 0.8, 1.0)


def learning_curve(
    name: str,
    data: Dataset,
    params: dict[str, Any],
    folds: int,
    seed: int,
    fractions: tuple[float, ...] = FRACTIONS,
) -> list[dict[str, float]]:
    """Brier on fixed test folds as the training part grows (nested prefixes of one shuffle).

    `params` are the final tuned values, so the curve shows the SHAPE (is it still falling?), not
    an unbiased level: those settings were chosen on all of this data.
    """
    rng = np.random.default_rng(seed)
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    splits = [
        (rng.permutation(train), test) for train, test in splitter.split(data.x, data.strata())
    ]
    curve = []
    for fraction in fractions:
        scores, sizes = [], []
        for train, test in splits:
            use = train[: max(2, int(round(fraction * len(train))))]
            fitted = fit_soft(name, params, data.x[use], data.y[use], data.names, seed)
            scores.append(brier(fitted.predict(data.x[test]), data.y[test]))
            sizes.append(len(use))
        curve.append(
            {
                "fraction": fraction,
                "train_profiles": float(np.mean(sizes)),
                "brier": float(np.mean(scores)),
                "brier_se": float(np.std(scores, ddof=1) / np.sqrt(len(scores))),
            }
        )
    return curve


def monotonicity_cost(
    name: str, data: Dataset, constrained: CvResult, repeats: int, folds: int, trials: int,
    seed: int,
) -> dict[str, Any]:  # fmt: skip
    """The winner without monotone constraints, tuned the same nested way on the same folds."""
    if name == "logistic":
        return {"applicable": False, "reason": "the logistic benchmark has no monotone constraints"}
    free = cross_validate(name, data, repeats, folds, trials, seed, constrained=False)
    delta, low, high = nadeau_bengio_interval(free, constrained)
    _, t, p = nadeau_bengio(free, constrained)
    return {
        "applicable": True,
        "brier_constrained": constrained.mean("brier"),
        "brier_unconstrained": free.mean("brier"),
        "delta_brier": delta,  # unconstrained minus constrained: negative means freedom helps
        "delta_ci": [low, high],
        "t": t,
        "p": p,
    }


def shortfall_definition(oof: np.ndarray, data: Dataset) -> dict[str, Any]:
    """The per-month definition against the cumulative one, on the development labels, and the
    out-of-fold predictions of the model trained on the cumulative label scored against both."""
    if data.label_monthly is None:
        return {"available": False, "reason": "the label file carries no per-month label"}
    agreement, confusion = band_agreement(data.label_monthly, data.y)
    return {
        "available": True,
        "mean_label_cumulative": float(data.y.mean()),
        "mean_label_monthly": float(data.label_monthly.mean()),
        "band_agreement_of_labels": agreement,
        "band_confusion_cumulative_rows_monthly_columns": confusion.tolist(),
        "brier_vs_cumulative": brier(oof, data.y),
        "brier_vs_monthly": brier(oof, data.label_monthly),
    }
