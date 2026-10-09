"""Train and compare the Engine 2 candidates: `python -m ml.engine2_train.train --config small|full`
(plan P5, tasks D6-D7). Writes `data/engine2/runs/<config>/` (gitignored); the report is built
from it by `ml.engine2_train.report`.

Order:
1. every tenth profile is set aside as the LOCKBOX (never used below this line);
2. nested grouped CV for each candidate on the development profiles -> the winner by the rule in
   `select.py`;
3. final hyperparameters tuned on the development profiles;
4. calibration chosen, and fitted, on single-repeat out-of-fold predictions of the development set;
5. the final calibrated winner scored once on the lockbox (with the logistic benchmark and the
   constant beside it);
6. ablation without the Engine 1 features (both arms tuned inside every fold, same folds), the
   same model without monotone constraints, a learning curve and the per-month shortfall
   definition as sensitivity runs.
"""

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from app.engines.risk.features import ENGINE1_FEATURES, FEATURE_NAMES, FEATURE_SCHEMA_HASH
from ml.engine2_train.calibrate import choose_calibration, fit_calibrator
from ml.engine2_train.cv import CvResult, cross_validate, nadeau_bengio, nadeau_bengio_interval
from ml.engine2_train.data import LABELS_PATH, Dataset, load_labels, split_lockbox
from ml.engine2_train.labelstats import baseline_facts
from ml.engine2_train.metrics import all_metrics, band_agreement, brier
from ml.engine2_train.models import CANDIDATES, fit_soft, tune
from ml.engine2_train.provenance import git_commit, library_versions, sha256_file
from ml.engine2_train.select import choose
from ml.engine2_train.sensitivity import learning_curve, monotonicity_cost, shortfall_definition

RUNS_DIR = Path(__file__).resolve().parents[3] / "data" / "engine2" / "runs"
RELIABILITY_BINS = 10
CALIBRATION_BASIS = "single-repeat out-of-fold predictions of the development set"


@dataclass(frozen=True)
class TrainConfig:
    name: str
    repeats: int
    folds: int
    trials: int
    seed: int = 20251228


CONFIGS = {
    "small": TrainConfig("small", repeats=1, folds=3, trials=3),
    "full": TrainConfig("full", repeats=5, folds=5, trials=12),
}


def _summary(result: CvResult) -> dict[str, Any]:
    keys = ("brier", "log_loss", "auc_at_030", "calibration_slope", "ece")
    groups = sorted({k for m in result.fold_metrics for k in m if k.startswith("brier@")})
    return {
        "folds": len(result.fold_metrics),
        **{f"{k}_mean": result.mean(k) for k in (*keys, *groups)},
        **{f"{k}_se": result.standard_error(k) for k in (*keys, *groups)},
        "brier_per_fold": [float(v) for v in result.metric("brier")],
        "chosen_params": result.chosen_params,
    }


def _ablation_row(without: CvResult, full: CvResult, key: str) -> dict[str, Any]:
    delta, low, high = nadeau_bengio_interval(without, full, key)
    _, t, p = nadeau_bengio(without, full, key)
    return {
        "brier_with_engine1": full.mean(key),
        "brier_without_engine1": without.mean(key),
        "delta_brier": delta,  # without minus with: positive means the forecast helps
        "delta_ci": [low, high],
        "t": t,
        "p": p,
    }


def _ablation(dev: Dataset, winner: str, full: CvResult, config: TrainConfig) -> dict[str, Any]:
    """Winner with and without the Engine 1 features. Both arms are tuned inside every training
    fold on the same folds: `full` IS the winner's nested CV from the model comparison (same data,
    folds, seed and trials), so it is reused rather than recomputed."""
    keep = tuple(n for n in FEATURE_NAMES if n not in ENGINE1_FEATURES)
    without = cross_validate(
        winner, dev.subset(keep), config.repeats, config.folds, config.trials, config.seed
    )
    row = _ablation_row(without, full, "brier")
    subgroups = {group: _ablation_row(without, full, f"brier@{group}") for group in dev.subgroups()}
    return {
        **row,
        "subgroups": subgroups,
        "removed_features": list(ENGINE1_FEATURES),
        "tuning": "nested in every fold, both arms",
        "ci_method": "Nadeau-Bengio corrected, t critical value for J - 1 degrees of freedom",
    }


def _reliability(pred: np.ndarray, target: np.ndarray) -> list[dict[str, float]]:
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


def _score_lockbox(
    lockbox: Dataset, raw: np.ndarray, calibrated: np.ndarray, benchmark: np.ndarray, base: float
) -> dict[str, Any]:
    """The one and only scoring of the final model on the lockbox."""
    agreement, confusion = band_agreement(calibrated, lockbox.y)
    groups = {
        group: {
            "profiles": int(mask.sum()),
            "brier_calibrated": brier(calibrated[mask], lockbox.y[mask]),
            "brier_benchmark": brier(benchmark[mask], lockbox.y[mask]),
            "brier_constant": brier(np.full(int(mask.sum()), base), lockbox.y[mask]),
        }
        for group, mask in lockbox.subgroups().items()
        if mask.any()
    }
    return {
        "profiles": len(lockbox),
        "raw": all_metrics(raw, lockbox.y),
        "calibrated": all_metrics(calibrated, lockbox.y),
        "logistic_benchmark_brier": brier(benchmark, lockbox.y),
        "constant_brier": brier(np.full(len(lockbox), base), lockbox.y),
        "band_agreement": agreement,
        "band_confusion_label_rows_model_columns": confusion.tolist(),
        "reliability": _reliability(calibrated, lockbox.y),
        "subgroups": groups,
    }


def _label_paths(labels_path: Path) -> int | None:
    """The Monte Carlo path count recorded beside the labels, if there is a manifest."""
    manifest = labels_path.parent / "MANIFEST.json"
    if not manifest.exists():
        return None
    return json.loads(manifest.read_text(encoding="utf-8")).get("paths")


def run(config: TrainConfig, labels_path: Path, out_dir: Path) -> dict[str, Any]:
    data = load_labels(labels_path)
    dev, lockbox = split_lockbox(data)
    paths = _label_paths(labels_path)
    results = {
        name: cross_validate(name, dev, config.repeats, config.folds, config.trials, config.seed)
        for name in CANDIDATES
    }
    choice = choose(results)
    winner = results[choice.winner]

    def tuned(name: str) -> dict[str, Any]:
        if config.trials <= 0:
            return {}
        return tune(name, dev.x, dev.y, dev.names, config.trials, config.seed, brier)

    final_params = tuned(choice.winner)
    oof = winner.oof[0]  # one repeat: every profile predicted once, by a model that did not see it
    calibration, calibration_scores = choose_calibration(oof, dev.y, seed=config.seed)
    calibrator = fit_calibrator(calibration, oof, dev.y)
    final = fit_soft(choice.winner, final_params, dev.x, dev.y, dev.names, config.seed)
    benchmark = fit_soft("logistic", tuned("logistic"), dev.x, dev.y, dev.names, config.seed)
    raw = final.predict(lockbox.x)
    lockbox_scores = _score_lockbox(
        lockbox, raw, calibrator.apply(raw), benchmark.predict(lockbox.x), float(dev.y.mean())
    )

    record = {
        "config": asdict(config),
        "profiles": len(data),
        "development_profiles": len(dev),
        "lockbox_profiles": len(lockbox),
        "strata": dev.n_strata,
        "label_facts": {
            "all": baseline_facts(data, paths),
            "development": baseline_facts(dev, paths),
        },
        "feature_schema_hash": FEATURE_SCHEMA_HASH,
        "labels_sha256": sha256_file(labels_path),
        "git_commit": git_commit(),
        "versions": library_versions(),
        "label_quantiles": {
            str(q): float(np.quantile(dev.y, q / 100)) for q in (5, 25, 50, 75, 95)
        },
        "models": {name: _summary(r) for name, r in results.items()},
        "winner": choice.winner,
        "best_by_brier": choice.best_by_brier,
        "reason": choice.reason,
        "holm_p_simpler_vs_best": choice.p_values,
        "versus_winner": {
            name: dict(zip(("delta", "t", "p"), nadeau_bengio(results[name], winner), strict=True))
            for name in CANDIDATES
            if name != choice.winner
        },
        "final_params": final_params,
        "calibration": {
            "chosen": calibration,
            "held_out_brier": calibration_scores,
            "fitted_on": CALIBRATION_BASIS,
            "parameters": calibrator.to_dict(),
        },
        "lockbox": lockbox_scores,
        "ablation": _ablation(dev, choice.winner, winner, config),
        "sensitivity": {
            "monotonicity": monotonicity_cost(
                choice.winner, dev, winner, config.repeats, config.folds, config.trials, config.seed
            ),
            "learning_curve": learning_curve(
                choice.winner, dev, final_params, config.folds, config.seed
            ),
            "shortfall_definition": shortfall_definition(oof, dev),
        },
        "constant_baseline_brier": brier(np.full(len(dev), dev.y.mean()), dev.y),
    }
    _save(out_dir, record, final, calibrator.to_dict(), oof)
    return record


def _save(out_dir: Path, record: dict, final, calibrator: dict, oof: np.ndarray) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (out_dir / "calibrator.json").write_text(
        json.dumps(calibrator, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    joblib.dump(final, out_dir / "final_model.joblib")
    np.save(out_dir / "oof_winner.npy", oof)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train and compare the Engine 2 candidates.")
    parser.add_argument("--config", choices=sorted(CONFIGS), default="small")
    parser.add_argument("--labels", type=Path, default=LABELS_PATH)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    config = CONFIGS[args.config]
    record = run(config, args.labels, args.out or RUNS_DIR / config.name)
    chosen = record["calibration"]["chosen"]
    print(f"winner: {record['winner']} ({record['reason']}); calibration: {chosen}")  # noqa: T201
    print(f"lockbox Brier (calibrated): {record['lockbox']['calibrated']['brier']:.4f}")  # noqa: T201


if __name__ == "__main__":
    main()
