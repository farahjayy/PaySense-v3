"""Calibration of the winner's probabilities, chosen by nested CV (plan P5, task D7).

Three options: none, Platt scaling (a logistic curve on the logit of the prediction) and isotonic
regression. Each is fitted on part of the out-of-fold predictions and scored on the rest, so the
choice never sees the data it is judged on. Soft targets are handled by duplicate-and-weight.
"""

from dataclasses import dataclass

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold

from ml.engine2_train.metrics import EPS, brier

OPTIONS = ("none", "platt", "isotonic")


@dataclass
class Calibrator:
    kind: str
    model: object | None = None

    def apply(self, pred: np.ndarray) -> np.ndarray:
        if self.kind == "none":
            return pred
        if self.kind == "platt":
            return self.model.predict_proba(_logit(pred).reshape(-1, 1))[:, 1]
        return self.model.predict(pred)


def _logit(p: np.ndarray) -> np.ndarray:
    clipped = np.clip(p, EPS, 1 - EPS)
    return np.log(clipped / (1 - clipped))


def fit_calibrator(kind: str, pred: np.ndarray, target: np.ndarray) -> Calibrator:
    if kind == "none":
        return Calibrator("none")
    if kind == "platt":
        x = np.concatenate([_logit(pred), _logit(pred)]).reshape(-1, 1)
        y = np.concatenate([np.ones(len(pred)), np.zeros(len(pred))])
        w = np.concatenate([target, 1 - target])
        return Calibrator(
            "platt", LogisticRegression(C=1e6, max_iter=1000).fit(x, y, sample_weight=w)
        )
    if kind == "isotonic":
        # a soft target is already a probability: regress it on the prediction, monotonically
        return Calibrator(
            "isotonic",
            IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(pred, target),
        )
    raise ValueError(f"unknown calibration {kind!r}; options are {OPTIONS}")


def choose_calibration(
    pred: np.ndarray, target: np.ndarray, folds: int = 5, seed: int = 0
) -> tuple[str, dict[str, float]]:
    """The option with the lowest held-out Brier score, and every option's score."""
    scores = {kind: [] for kind in OPTIONS}
    for train, test in KFold(folds, shuffle=True, random_state=seed).split(pred):
        for kind in OPTIONS:
            fitted = fit_calibrator(kind, pred[train], target[train])
            scores[kind].append(brier(fitted.apply(pred[test]), target[test]))
    mean = {kind: float(np.mean(values)) for kind, values in scores.items()}
    return min(mean, key=mean.get), mean
