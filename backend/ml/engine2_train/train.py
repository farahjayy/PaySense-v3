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

Engine v3 (plan 2026-10-18-engine-v3 §5): the target is two-part by default (D-62): the models
learn q from the features with weight 1 - b and are scored on b + (1 - b) * q-hat; the calibrator
is chosen on that composed Brier and fitted on q-hat. When the labels hold profiles from index
10,000 on, those are the new lockbox; the old every-tenth lockbox is kept out of every step and
scored once beside it as continuity. The predict-p_without benchmark is scored on both.
"""

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from app.engines.risk.artefact import live_constants
from app.engines.risk.features import ENGINE1_FEATURES, FEATURE_SCHEMA_HASH
from ml.engine2_train.calibrate import Calibrator, choose_calibration, fit_calibrator
from ml.engine2_train.cv import CvResult, cross_validate, nadeau_bengio, nadeau_bengio_interval
from ml.engine2_train.data import (
    LABELS_PATH,
    Dataset,
    continuity_lockbox,
    load_labels,
    split_lockbox,
)
from ml.engine2_train.labelstats import baseline_facts
from ml.engine2_train.lockbox import LOG_FILE as LOCKBOX_LOG
from ml.engine2_train.lockbox import append_log, score_lockbox
from ml.engine2_train.metrics import brier
from ml.engine2_train.models import (
    CANDIDATES,
    Fitted,
    fit_soft,
    logistic_sign_check,
    tune,
    two_part_target,
)
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
    target: str = "two_part"  # engine v3 (D-62); "direct" is the v2 target, p_with itself


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
    keep = tuple(n for n in dev.names if n not in ENGINE1_FEATURES)  # the base column stays
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
    keys = ("label_version", "horizon_max_weeks", "served_model_files", "paths", "seed",
            "band_rule_sha256", "recentre_errors")  # fmt: skip
    return {
        "labels_manifest": {key: manifest.get(key) for key in keys},
        "serving_constants": live_constants(),
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


def _log_scoring(
    out_dir: Path, record: dict[str, Any], scores: dict[str, Any], lockbox: str = ""
) -> int:
    """Append this scoring to the log beside the run directories; return how many it holds.
    `lockbox` names which lockbox was scored when a label file holds two (engine v3)."""
    commit = record["git_commit"]
    run_id = f"{record['config']['name']}-{record['labels_sha256'][:12]}-{str(commit)[:12]}"
    entry = {
        "run_id": run_id,
        "git_commit": commit,
        "labels_sha256": record["labels_sha256"],
        "winner": record["winner"],
        "lockbox_brier_calibrated": scores["calibrated"]["brier"],
        "lockbox_brier_raw": scores["raw"]["brier"],
    }
    if lockbox:
        entry["lockbox"] = lockbox
    return append_log(out_dir.parent / LOCKBOX_LOG, entry)


def calibrated_predict(final: Fitted, calibrator: Calibrator, x: np.ndarray) -> np.ndarray:
    """What the served artefact computes: the calibrated q composed on the base for a two-part
    model, the calibrated probability otherwise."""
    if not final.two_part:
        return calibrator.apply(final.predict(x))
    base = x[:, -1]
    return base + (1 - base) * calibrator.apply(final.predict_q(x[:, :-1]))


def load_run(run_dir: Path) -> tuple[Fitted, Calibrator]:
    final = joblib.load(run_dir / "final_model.joblib")
    stored = json.loads((run_dir / "calibrator.json").read_text(encoding="utf-8"))
    return final, Calibrator.from_dict(stored)


def _q_of(composed: np.ndarray, base: np.ndarray) -> np.ndarray:
    """q-hat back from a composed prediction (0 where b = 1, where q has no weight)."""
    gap = 1 - base
    return np.where(gap > 0, np.clip((composed - base) / np.where(gap > 0, gap, 1), 0, 1), 0.0)


def _calibration(oof: np.ndarray, dev: Dataset, two_part: bool, seed: int):
    """Choose and fit the calibrator: on the probability (direct) or on q-hat with weight 1 - b,
    scored on the composed probability (two-part)."""
    if not two_part:
        chosen, scores = choose_calibration(oof, dev.y, seed=seed)
        return chosen, scores, fit_calibrator(chosen, oof, dev.y)
    base = dev.x[:, -1]
    q, weight = two_part_target(dev.y, base)
    q_hat = _q_of(oof, base)
    chosen, scores = choose_calibration(q_hat, q, seed=seed, weight=weight, base=base)
    return chosen, scores, fit_calibrator(chosen, q_hat, q, weight)


def _benchmarks(box: Dataset, dev: Dataset, two_part: bool) -> dict[str, np.ndarray]:
    if box.p_without is None:
        return {}
    out = {"p_without": box.p_without}
    if dev.p_without is not None:
        mean_q = float(two_part_target(dev.y, dev.p_without)[0].mean())
        out["p_without_plus_mean_q"] = box.p_without + (1 - box.p_without) * mean_q
    return out


def check_labels_match_serving(manifest: dict[str, Any]) -> None:
    """A served model learns only from labels made the way serving works (D-56, ml-audit M1):
    never the re-centred analysis labels, never labels made with another band table."""
    if manifest.get("recentre_errors"):
        raise ValueError("these labels re-centre the error record (D-56 analysis only); train on "
                         "the served labels")  # fmt: skip
    made_with = manifest.get("band_rule_sha256")
    if made_with is not None and made_with != live_constants()["BAND_RULE_SHA256"]:
        raise ValueError("these labels were made with another band table than the code's; "
                         "make the labels again")  # fmt: skip


def run(config: TrainConfig, labels_path: Path, out_dir: Path) -> dict[str, Any]:
    manifest = _manifest(labels_path)
    check_labels_match_serving(manifest)
    data = load_labels(labels_path)
    two_part = config.target == "two_part"
    if two_part:
        data = data.with_base()
    elif config.target != "direct":
        raise ValueError(f"unknown target {config.target!r}")
    dev, lockbox = split_lockbox(data)
    continuity = continuity_lockbox(data)
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
    calibration, calibration_scores, calibrator = _calibration(oof, dev, two_part, config.seed)
    final = fit_soft(choice.winner, final_params, dev.x, dev.y, dev.names, config.seed)
    benchmark = fit_soft("logistic", tuned("logistic"), dev.x, dev.y, dev.names, config.seed)

    record = {
        "config": asdict(config),
        "target": config.target,
        "profiles": len(data),
        "development_profiles": len(dev),
        "lockbox_profiles": len(lockbox),
        "continuity_profiles": len(continuity),
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
    def scored(box: Dataset) -> dict[str, Any]:
        return score_lockbox(
            box, final.predict(box.x), calibrated_predict(final, calibrator, box.x),
            benchmark.predict(box.x), float(dev.y.mean()), _group_bases(dev),
            _benchmarks(box, dev, two_part),
        )  # fmt: skip

    scores = scored(lockbox)
    record["lockbox"] = scores
    record["lockbox_scorings"] = _log_scoring(
        out_dir, record, scores, "new" if len(continuity) else ""
    )
    if len(continuity):
        record["continuity"] = scored(continuity)
        record["continuity_scorings"] = _log_scoring(
            out_dir, record, record["continuity"], "old (continuity)"
        )
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
