"""Train and compare the Engine 2 candidates: `python -m ml.engine2_train.train --config small|full`
(plan P5, tasks D6-D7). Writes `data/engine2/runs/<config>/` (gitignored); the report is built
from it by `ml.engine2_train.report`.

Order:
1. every tenth profile is set aside as the LOCKBOX (never used below this line);
2. nested grouped CV for each candidate on the development profiles -> the winner by the rule in
   `select.py`;
3. final hyperparameters tuned on the development profiles;
4. calibration chosen, and fitted, on single-repeat out-of-fold predictions of the development set;
5. ablation without the Engine 1 features and the same model without monotone constraints (both
   arms of each computed fresh, on folds the model comparison never used), a learning curve and
   the per-month shortfall definition as sensitivity runs;
6. LAST, the final calibrated winner scored once on the lockbox (with the logistic benchmark and
   the constants beside it), and that scoring appended to `data/engine2/runs/lockbox_log.jsonl`.
   Everything that can fail is done before step 6, so a crash cannot spend the lockbox.
"""

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from app.engines.forecasting.service import DASHBOARD_MONTHS, ERROR_INFLATION
from app.engines.forecasting.simulate import BOOTSTRAP_BLOCK, RISK_CHECK_MAX_WEEKS
from app.engines.risk.features import ENGINE1_FEATURES, FEATURE_NAMES, FEATURE_SCHEMA_HASH
from ml.engine2_train.calibrate import choose_calibration, fit_calibrator
from ml.engine2_train.cv import CvResult, cross_validate, nadeau_bengio, nadeau_bengio_interval
from ml.engine2_train.data import LABELS_PATH, Dataset, load_labels, split_lockbox
from ml.engine2_train.labelstats import baseline_facts
from ml.engine2_train.lockbox import LOG_FILE as LOCKBOX_LOG
from ml.engine2_train.lockbox import append_log, score_lockbox
from ml.engine2_train.metrics import brier
from ml.engine2_train.models import CANDIDATES, Fitted, fit_soft, logistic_sign_check, tune
from ml.engine2_train.provenance import git_commit, library_versions, sha256_file
from ml.engine2_train.select import choose
from ml.engine2_train.sensitivity import learning_curve, monotonicity_cost, shortfall_definition

RUNS_DIR = Path(__file__).resolve().parents[3] / "data" / "engine2" / "runs"
FRESH_FOLDS_OFFSET = 1000  # the ablation and monotonicity arms use folds selection never saw
CALIBRATION_BASIS = "single-repeat out-of-fold predictions of the development set"
CALIBRATION_APPLIED_TO = (
    "the final model, which has other hyperparameters (tuned on all development profiles) and "
    "more training data than the fold models whose predictions fitted the calibrator"
)


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


def _ablation(dev: Dataset, winner: str, config: TrainConfig) -> dict[str, Any]:
    """Winner with and without the Engine 1 features. BOTH arms are computed here, tuned inside
    every training fold, on the same fresh folds: neither is the model comparison's run of the
    winner, which was selected for being the best and would carry a winner's curse that the other
    arm lacks."""
    keep = tuple(n for n in FEATURE_NAMES if n not in ENGINE1_FEATURES)
    seed = config.seed + FRESH_FOLDS_OFFSET
    full = cross_validate(winner, dev, config.repeats, config.folds, config.trials, seed)
    without = cross_validate(
        winner, dev.subset(keep), config.repeats, config.folds, config.trials, seed
    )
    row = _ablation_row(without, full, "brier")
    subgroups = {group: _ablation_row(without, full, f"brier@{group}") for group in dev.subgroups()}
    return {
        **row,
        "subgroups": subgroups,
        "removed_features": list(ENGINE1_FEATURES),
        "tuning": "nested in every fold, both arms",
        "arms": "both computed fresh on the same folds, which the model comparison did not use",
        "fresh_folds_seed": seed,
        "ci_method": "Nadeau-Bengio corrected, t critical value for J - 1 degrees of freedom",
    }


def _manifest(labels_path: Path) -> dict[str, Any]:
    """The label manifest recorded beside the labels, or {} if there is none."""
    path = labels_path.parent / "MANIFEST.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _group_bases(dev: Dataset) -> dict[str, float]:
    """The development mean label of each subgroup: that subgroup's own constant benchmark."""
    return {
        group: float(dev.y[mask].mean()) for group, mask in dev.subgroups().items() if mask.any()
    }


def _serving_facts(manifest: dict[str, Any]) -> dict[str, Any]:
    """What a serving artefact's metadata needs from the labels and the code (P6)."""
    keys = ("label_version", "horizon_max_weeks", "served_model_files", "paths", "seed")
    return {
        "labels_manifest": {key: manifest.get(key) for key in keys},
        "serving_constants": {
            "RISK_CHECK_MAX_WEEKS": RISK_CHECK_MAX_WEEKS,
            "DASHBOARD_MONTHS": DASHBOARD_MONTHS,
            "ERROR_INFLATION": ERROR_INFLATION,
            "BOOTSTRAP_BLOCK": BOOTSTRAP_BLOCK,
        },
    }


def _signs(benchmark: Fitted) -> dict[str, Any]:
    """Do the logistic coefficients point the way the monotone constraints force the others?"""
    rows = logistic_sign_check(benchmark)
    verdicts = [r["agrees"] for r in rows if r["agrees"] is not None]
    return {
        "features": rows,
        "constrained_features": len(verdicts),
        "agree": int(sum(verdicts)),
        "disagree": int(len(verdicts) - sum(verdicts)),
    }


def _sensitivity(
    dev: Dataset, winner: str, final_params: dict[str, Any], oof: np.ndarray, config: TrainConfig
) -> dict[str, Any]:
    fresh = config.seed + FRESH_FOLDS_OFFSET
    return {
        "monotonicity": monotonicity_cost(
            winner, dev, config.repeats, config.folds, config.trials, fresh
        ),
        "learning_curve": learning_curve(winner, dev, final_params, config.folds, config.seed),
        "shortfall_definition": shortfall_definition(oof, dev),
    }


def _log_scoring(out_dir: Path, record: dict[str, Any], scores: dict[str, Any]) -> int:
    """Append this scoring to the log beside the run directories; return how many it holds."""
    commit = record["git_commit"]
    run_id = f"{record['config']['name']}-{record['labels_sha256'][:12]}-{str(commit)[:12]}"
    return append_log(
        out_dir.parent / LOCKBOX_LOG,
        {
            "run_id": run_id,
            "git_commit": commit,
            "labels_sha256": record["labels_sha256"],
            "winner": record["winner"],
            "lockbox_brier_calibrated": scores["calibrated"]["brier"],
            "lockbox_brier_raw": scores["raw"]["brier"],
        },
    )


def run(config: TrainConfig, labels_path: Path, out_dir: Path) -> dict[str, Any]:
    data = load_labels(labels_path)
    dev, lockbox = split_lockbox(data)
    manifest = _manifest(labels_path)
    paths = manifest.get("paths")
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
        **_serving_facts(manifest),
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
            "applied_to": CALIBRATION_APPLIED_TO,
            "parameters": calibrator.to_dict(),
        },
        "logistic_signs": _signs(benchmark),
        "served_model_has_monotone_constraints": choice.winner != "logistic",
        "ablation": _ablation(dev, choice.winner, config),
        "sensitivity": _sensitivity(dev, choice.winner, final_params, oof, config),
        "constant_baseline_brier": brier(np.full(len(dev), dev.y.mean()), dev.y),
    }
    # the last step: the one scoring of the final model on the lockbox, then its log line
    raw = final.predict(lockbox.x)
    scores = score_lockbox(
        lockbox, raw, calibrator.apply(raw), benchmark.predict(lockbox.x),
        float(dev.y.mean()), _group_bases(dev),
    )  # fmt: skip
    record["lockbox"] = scores
    record["lockbox_scorings"] = _log_scoring(out_dir, record, scores)
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
    print(f"lockbox scorings logged: {record['lockbox_scorings']}")  # noqa: T201


if __name__ == "__main__":
    main()
