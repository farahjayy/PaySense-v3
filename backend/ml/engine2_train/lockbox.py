"""The one scoring of the final model on the lockbox, and the log that counts it
(plan P5; audit passes 1 and 2).

* The constant benchmark of a subgroup uses that subgroup's OWN development mean, not the overall
  one (the low-baseline subgroup's labels average about 0.07, the whole set's about 0.44).
* The low-baseline subgroup is scored in full: Brier, the other metrics, band agreement and
  reliability, for the raw and the calibrated model.
* A descriptive Brier breakdown by label class (exactly 0, between, exactly 1) and by whether the
  baseline is strictly between 0 and 1 shows how much of every score is the trivial profiles.
* Every scoring is appended to an append-only log, so the report can say how often the lockbox
  has been used.
"""

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from ml.engine2_train.data import Dataset
from ml.engine2_train.metrics import all_metrics, band_agreement, brier

RELIABILITY_BINS = 10
LOG_FILE = "lockbox_log.jsonl"
CONSTANT_BASIS = "development mean of the subgroup"


def reliability(pred: np.ndarray, target: np.ndarray) -> list[dict[str, float]]:
    edges = np.linspace(0, 1, RELIABILITY_BINS + 1)
    which = np.clip(np.searchsorted(edges, pred, side="right") - 1, 0, RELIABILITY_BINS - 1)
    return [
        {
            "bin": b,
            "profiles": int((which == b).sum()),
            "mean_prediction": float(pred[which == b].mean()),
            "mean_label": float(target[which == b].mean()),
        }
        for b in range(RELIABILITY_BINS)
        if (which == b).any()
    ]


def _finite(metrics: dict[str, float]) -> dict[str, float | None]:
    """NaN (a metric that is undefined on a subset, e.g. one class only) becomes null."""
    return {k: (None if math.isnan(v) else v) for k, v in metrics.items()}


def _briers(
    raw: np.ndarray, calibrated: np.ndarray, benchmark: np.ndarray, y: np.ndarray, constant: float
) -> dict[str, float]:
    return {
        "brier_calibrated": brier(calibrated, y),
        "brier_raw": brier(raw, y),
        "brier_benchmark": brier(benchmark, y),
        "brier_constant": brier(np.full(len(y), constant), y),
    }


def _subgroup(
    mask: np.ndarray, raw: np.ndarray, calibrated: np.ndarray, benchmark: np.ndarray,
    y: np.ndarray, constant: float,
) -> dict[str, Any]:  # fmt: skip
    r, c, b, t = raw[mask], calibrated[mask], benchmark[mask], y[mask]
    agreement, confusion = band_agreement(c, t)
    return {
        "profiles": int(mask.sum()),
        **_briers(r, c, b, t, constant),
        "constant_value": constant,
        "constant_basis": CONSTANT_BASIS,
        "raw": _finite(all_metrics(r, t)),
        "calibrated": _finite(all_metrics(c, t)),
        "band_agreement": agreement,
        "band_confusion_label_rows_model_columns": confusion.tolist(),
        "reliability": reliability(c, t),
    }


def brier_breakdown(
    lockbox: Dataset, raw: np.ndarray, calibrated: np.ndarray, benchmark: np.ndarray, base: float
) -> dict[str, dict[str, float]]:
    """Descriptive only: the lockbox Brier split by label class and by baseline. `base` is the
    development mean (the overall constant). A class with no profile is left out."""
    y = lockbox.y
    classes = {
        "label_exactly_0": y == 0,
        "label_between_0_and_1": (y > 0) & (y < 1),
        "label_exactly_1": y == 1,
    }
    if lockbox.p_without is not None:
        p = lockbox.p_without
        classes["p_without_between_0_and_1"] = (p > 0) & (p < 1)
        classes["p_without_exactly_0_or_1"] = (p <= 0) | (p >= 1)
    total = float(((calibrated - y) ** 2).sum()) or 1.0
    return {
        name: {
            "profiles": int(mask.sum()),
            "share_of_lockbox": float(mask.mean()),
            **_briers(raw[mask], calibrated[mask], benchmark[mask], y[mask], base),
            "share_of_squared_error": float(((calibrated[mask] - y[mask]) ** 2).sum() / total),
        }
        for name, mask in classes.items()
        if mask.any()
    }


def _band_index(p: np.ndarray) -> np.ndarray:
    return np.searchsorted([0.10, 0.30], np.asarray(p, dtype=float), side="right")


def purchase_moves_band(
    lockbox: Dataset, predictions: dict[str, np.ndarray]
) -> dict[str, Any] | None:
    """Where the purchase changes the band (band of p_without != band of the label): the profiles
    where the decision is about the purchase. Brier, mean absolute error (the error of the added
    risk, since every model here shares the exact b) and band agreement, per prediction."""
    if lockbox.p_without is None:
        return None
    mask = _band_index(lockbox.p_without) != _band_index(lockbox.y)
    out: dict[str, Any] = {"profiles": int(mask.sum()), "share": float(mask.mean())}
    if not mask.any():
        return out
    y = lockbox.y[mask]
    for name, pred in predictions.items():
        agreement, _ = band_agreement(pred[mask], y)
        out[name] = {
            "brier": brier(pred[mask], y),
            "mae": float(np.mean(np.abs(pred[mask] - y))),
            "band_agreement": agreement,
        }
    return out


def score_lockbox(
    lockbox: Dataset, raw: np.ndarray, calibrated: np.ndarray, benchmark: np.ndarray,
    base: float, group_bases: dict[str, float],
    benchmarks: dict[str, np.ndarray] | None = None,
) -> dict[str, Any]:  # fmt: skip
    """The final model on the lockbox. `base` is the development mean label; `group_bases` the
    development mean of each subgroup (its own constant benchmark). `benchmarks` are further
    predictions scored beside it (engine v3: predict p_without, and p_without plus the mean
    added share)."""
    agreement, confusion = band_agreement(calibrated, lockbox.y)
    constant = np.full(len(lockbox), base)
    everything = {"model": calibrated, "logistic": benchmark, "constant": constant}
    everything.update(benchmarks or {})
    groups = {
        group: _subgroup(mask, raw, calibrated, benchmark, lockbox.y, group_bases.get(group, base))
        for group, mask in lockbox.subgroups().items()
        if mask.any()
    }
    return {
        "profiles": len(lockbox),
        "raw": _finite(all_metrics(raw, lockbox.y)),
        "calibrated": _finite(all_metrics(calibrated, lockbox.y)),
        "logistic_benchmark_brier": brier(benchmark, lockbox.y),
        "constant_brier": brier(np.full(len(lockbox), base), lockbox.y),
        "band_agreement": agreement,
        "band_confusion_label_rows_model_columns": confusion.tolist(),
        "reliability": reliability(calibrated, lockbox.y),
        "subgroups": groups,
        "brier_by_class": brier_breakdown(lockbox, raw, calibrated, benchmark, base),
        "mae": float(np.mean(np.abs(calibrated - lockbox.y))),
        "benchmarks": {
            name: {
                "brier": brier(pred, lockbox.y),
                "mae": float(np.mean(np.abs(pred - lockbox.y))),
                "band_agreement": band_agreement(pred, lockbox.y)[0],
            }
            for name, pred in everything.items()
            if name != "model"
        },
        "purchase_moves_band": purchase_moves_band(lockbox, everything),
    }


def append_log(path: Path, entry: dict[str, Any]) -> int:
    """Append one scoring to the log and return how many scorings it now holds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0
    line = {**entry, "scoring": existing + 1}
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(line, sort_keys=True) + "\n")
    return existing + 1
