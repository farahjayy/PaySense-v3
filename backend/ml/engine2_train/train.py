"""Train and compare the Engine 2 candidates: `python -m ml.engine2_train.train --config small|full`
(plan P5, tasks D6-D7). Writes `data/engine2/runs/<config>/` (gitignored); the report is built
from it by `ml.engine2_train.report`.

Order: nested grouped CV for each candidate -> the winner by the rule in `select.py` -> final
hyperparameters tuned on all data -> calibration chosen by nested CV on the out-of-fold
predictions -> ablation without the Engine 1 features -> unconstrained sensitivity run.
"""

import argparse
import json
import platform
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import xgboost

from app.engines.risk.features import ENGINE1_FEATURES, FEATURE_NAMES, FEATURE_SCHEMA_HASH
from ml.engine2_train.calibrate import choose_calibration
from ml.engine2_train.cv import CvResult, cross_validate, nadeau_bengio
from ml.engine2_train.data import LABELS_PATH, Dataset, load_labels
from ml.engine2_train.metrics import brier
from ml.engine2_train.models import CANDIDATES, tune
from ml.engine2_train.select import choose

RUNS_DIR = Path(__file__).resolve().parents[3] / "data" / "engine2" / "runs"


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
    return {
        "folds": len(result.fold_metrics),
        **{f"{k}_mean": result.mean(k) for k in keys},
        **{f"{k}_se": result.standard_error(k) for k in keys},
        "brier_per_fold": [float(v) for v in result.metric("brier")],
        "chosen_params": result.chosen_params,
    }


def _ablation(
    data: Dataset, winner: str, params: dict[str, Any], config: TrainConfig
) -> dict[str, Any]:
    """Winner with and without the Engine 1 features, same settings and same folds."""
    keep = tuple(n for n in FEATURE_NAMES if n not in ENGINE1_FEATURES)
    kwargs = dict(
        repeats=config.repeats, k=config.folds, seed=config.seed, fixed_params=params, trials=0
    )
    full = cross_validate(winner, data, **kwargs)
    without = cross_validate(winner, data.subset(keep), **kwargs)
    mean, t, p = nadeau_bengio(without, full)
    d = without.metric("brier") - full.metric("brier")
    train, test = full.fold_sizes[0]
    half_width = 1.96 * float(np.sqrt((1 / len(d) + test / train) * np.var(d, ddof=1)))
    return {
        "brier_with_engine1": full.mean("brier"),
        "brier_without_engine1": without.mean("brier"),
        "delta_brier": mean,  # without minus with: positive means the forecast helps
        "delta_ci": [mean - half_width, mean + half_width],
        "t": t,
        "p": p,
        "removed_features": list(ENGINE1_FEATURES),
    }


def run(config: TrainConfig, labels_path: Path, out_dir: Path) -> dict[str, Any]:
    data = load_labels(labels_path)
    results: dict[str, CvResult] = {}
    for name in CANDIDATES:
        results[name] = cross_validate(
            name, data, config.repeats, config.folds, config.trials, config.seed
        )
    choice = choose(results)

    final_params = (
        tune(choice.winner, data.x, data.y, data.names, config.trials, config.seed, brier)
        if config.trials > 0
        else {}
    )
    oof = np.nanmean(results[choice.winner].oof, axis=0)
    calibration, calibration_scores = choose_calibration(oof, data.y, seed=config.seed)
    ablation = _ablation(data, choice.winner, final_params, config)

    comparisons = {
        name: dict(
            zip(
                ("delta", "t", "p"),
                nadeau_bengio(results[name], results[choice.winner]),
                strict=True,
            )
        )
        for name in CANDIDATES
        if name != choice.winner
    }
    record = {
        "config": asdict(config),
        "profiles": len(data),
        "feature_schema_hash": FEATURE_SCHEMA_HASH,
        "label_quantiles": {
            str(q): float(np.quantile(data.y, q / 100)) for q in (5, 25, 50, 75, 95)
        },
        "models": {name: _summary(r) for name, r in results.items()},
        "winner": choice.winner,
        "best_by_brier": choice.best_by_brier,
        "reason": choice.reason,
        "holm_p_simpler_vs_best": choice.p_values,
        "versus_winner": comparisons,
        "final_params": final_params,
        "calibration": {"chosen": calibration, "held_out_brier": calibration_scores},
        "ablation": ablation,
        "constant_baseline_brier": brier(np.full(len(data), data.y.mean()), data.y),
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "xgboost": xgboost.__version__,
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    np.save(out_dir / "oof_winner.npy", oof)
    return record


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


if __name__ == "__main__":
    main()
