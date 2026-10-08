"""Metrics against a SOFT target (plan P5, task D6).

The label is a probability, not a 0/1 outcome, so the primary score is the Brier score against
that probability: mean squared difference between prediction and label.
"""

import math

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

CAUTION_THRESHOLD = 0.30  # the pre-registered At Risk boundary, used for the hard-label AUC
EPS = 1e-6
ECE_BINS = 10


def brier(pred: np.ndarray, target: np.ndarray) -> float:
    return float(np.mean((pred - target) ** 2))


def soft_log_loss(pred: np.ndarray, target: np.ndarray) -> float:
    p = np.clip(pred, EPS, 1 - EPS)
    return float(-np.mean(target * np.log(p) + (1 - target) * np.log(1 - p)))


def auc_at_threshold(pred: np.ndarray, target: np.ndarray) -> float:
    """ROC-AUC for telling At Risk (label >= 0.30) from the rest; NaN if one class is missing."""
    hard = target >= CAUTION_THRESHOLD
    if hard.all() or not hard.any():
        return math.nan
    return float(roc_auc_score(hard, pred))


def calibration_slope(pred: np.ndarray, target: np.ndarray) -> float:
    """Slope of the soft target on logit(prediction): 1 is perfectly calibrated, below 1 means the
    predictions are too extreme. Fitted by duplicate-and-weight logistic regression."""
    logit = np.log(np.clip(pred, EPS, 1 - EPS) / (1 - np.clip(pred, EPS, 1 - EPS)))
    x = np.concatenate([logit, logit]).reshape(-1, 1)
    y = np.concatenate([np.ones(len(pred)), np.zeros(len(pred))])
    w = np.concatenate([target, 1 - target])
    if np.ptp(logit) == 0:
        return math.nan
    model = LogisticRegression(C=1e6, max_iter=1000).fit(x, y, sample_weight=w)
    return float(model.coef_[0][0])


def expected_calibration_error(pred: np.ndarray, target: np.ndarray) -> float:
    edges = np.linspace(0, 1, ECE_BINS + 1)
    which = np.clip(np.searchsorted(edges, pred, side="right") - 1, 0, ECE_BINS - 1)
    total = 0.0
    for b in range(ECE_BINS):
        mask = which == b
        if mask.any():
            total += mask.mean() * abs(float(target[mask].mean()) - float(pred[mask].mean()))
    return float(total)


def all_metrics(pred: np.ndarray, target: np.ndarray) -> dict[str, float]:
    return {
        "brier": brier(pred, target),
        "log_loss": soft_log_loss(pred, target),
        "auc_at_030": auc_at_threshold(pred, target),
        "calibration_slope": calibration_slope(pred, target),
        "ece": expected_calibration_error(pred, target),
    }
