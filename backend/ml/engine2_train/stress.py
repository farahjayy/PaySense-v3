"""Stress tests for the trained Engine 2 model (plan P5, task D7):

    cd backend && uv run python -m ml.engine2_train.stress --config full

Each variant perturbs what the product knows about a profile (its LEDGER, or the recurring items
detected from it), then runs the whole pipeline again (detection, Engine 1, features) and asks: does
the final calibrated model still track what the simulation says?

Only the LOCKBOX profiles are used (every tenth, set aside before any selection, tuning or
calibration in `train.py`), and every variant is scored with the stored calibrated final model. The
`identity` variant re-runs the unperturbed pipeline with the same path count and seed, so every
comparison is like for like (it should reproduce the stored labels exactly). Variants: income down
20%, a ledger that stopped three weeks ago, a missing month, and the next PTPTN disbursement not
arriving. Stale or incomplete ledgers are never trained on (audit M5): this is a robustness
evaluation, and training on them would contaminate it.
"""

import argparse
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np

from app.domain.categorize import REFUND, TRANSFER
from app.domain.schedule import add_months
from app.engines.forecasting.flows import SEMESTER_MONTHS, occurrences
from app.engines.forecasting.serving import served_forecaster
from app.engines.forecasting.simulate import RISK_CHECK_MAX_WEEKS, Forecaster
from app.engines.forecasting.summary import build_feature_inputs
from app.engines.risk.features import FEATURE_SCHEMA_HASH, as_vector, compute_features
from ml.datagen.params import Params, load_params
from ml.datagen.profile import generate_dated_profile
from ml.engine2_train.data import LABELS_PATH, load_labels, split_lockbox
from ml.engine2_train.labels import (
    LABEL_VERSION,
    MANIFEST_FILE,
    prepare,
    profile_seed,
    served_model_files,
)
from ml.engine2_train.metrics import band_agreement, brier
from ml.engine2_train.provenance import sha256_file
from ml.engine2_train.train import RUNS_DIR, calibrated_predict, load_run

Rows = list[dict[str, Any]]
Transform = Callable[[Rows, date], Rows]
INCOME_FACTOR = 0.8
STALE_DAYS = 21
PTPTN_LOOKAHEAD_DAYS = 200  # a little more than one semester: the next disbursement is inside


class Variant(NamedTuple):
    """What changes: the ledger before detection, and/or the recurring items after it."""

    rows: Transform | None = None
    items: Transform | None = None


def income_down(rows: Rows, as_of: date) -> Rows:
    return [
        {**r, "amount_sen": round(r["amount_sen"] * INCOME_FACTOR)}
        if r["type"] == "income" and r["category"] not in (REFUND, TRANSFER)
        else r
        for r in rows
    ]


def stale(rows: Rows, as_of: date) -> Rows:
    return [r for r in rows if r["date"] <= as_of - timedelta(days=STALE_DAYS)]


def missing_month(rows: Rows, as_of: date) -> Rows:
    last = date(as_of.year, as_of.month, 1) - timedelta(days=1)  # the month before as-of
    return [r for r in rows if (r["date"].year, r["date"].month) != (last.year, last.month)]


def ptptn_delayed(items: Rows, as_of: date) -> Rows:
    """The next semester-funded income does not arrive (PRD 3.1, D-10): the recurring PTPTN item's
    anchor moves one semester on, so its next occurrence after `as_of` is gone and the later ones
    are unchanged. A student whose ledger holds no detected semester income is not changed: the
    product has no PTPTN disbursement to delay."""
    out = []
    for item in items:
        if item["kind"] == "income" and item["cadence"] == "semester":
            upcoming = occurrences(
                item, as_of + timedelta(days=1), as_of + timedelta(days=PTPTN_LOOKAHEAD_DAYS)
            )
            if upcoming:
                item = {**item, "anchor_date": add_months(upcoming[0], SEMESTER_MONTHS)}
        out.append(item)
    return out


VARIANTS: dict[str, Variant] = {
    "identity": Variant(),
    "income_down_20": Variant(rows=income_down),
    "stale_3_weeks": Variant(rows=stale),
    "missing_month": Variant(rows=missing_month),
    "ptptn_delayed": Variant(items=ptptn_delayed),
}


@dataclass(frozen=True)
class VariantRun:
    """Features and labels of the profiles that were not locked under a variant."""

    indices: tuple[int, ...]
    vectors: np.ndarray
    labels: np.ndarray
    locked: int
    changed: tuple[bool, ...]  # did the variant alter what the product knew about the profile
    bases: np.ndarray | None = None  # the simulated chance without the purchase (two-part, D-62)

    def design(self, with_base: bool = False) -> np.ndarray:
        """The model's input: features, plus the base as a last column for a two-part model."""
        if not with_base:
            return self.vectors
        if self.bases is None:
            raise ValueError("this run did not keep the base the two-part model needs")
        return np.column_stack([self.vectors, self.bases])

    def summary(
        self, predict: Callable[[np.ndarray], np.ndarray], with_base: bool = False
    ) -> dict[str, Any]:
        if not len(self.labels):
            return {"profiles": 0, "locked": self.locked}
        pred = predict(self.design(with_base))
        agreement, _ = band_agreement(pred, self.labels)
        return {
            "profiles": len(self.labels),
            "locked": self.locked,
            "changed_inputs": int(sum(self.changed)),
            "brier": brier(pred, self.labels),
            "mean_prediction": float(pred.mean()),
            "mean_label": float(self.labels.mean()),
            "band_agreement": agreement,
        }


def run_variant(
    params: Params,
    master_seed: int,
    indices: Sequence[int],
    variant: Variant,
    forecaster: Forecaster,
    paths: int,
) -> VariantRun:
    """Re-run the pipeline on perturbed profiles with the labels' own path count and seeds."""
    found, vectors, labels, changed, bases, locked = [], [], [], [], [], 0
    for index in indices:
        profile = generate_dated_profile(params, master_seed, index)
        known = prepare(profile, variant.rows, variant.items)
        built = build_feature_inputs(
            rows=known["rows"], items=known["items"], plans=known["plans"],
            proposal=known["proposal"], provider_limits=known["limits"], today=known["as_of"],
            forecaster=forecaster, seed=profile_seed(master_seed, index), paths=paths,
            savings_buffer_sen=known["savings_buffer_sen"],
        )  # fmt: skip
        if built is None:
            locked += 1
            continue
        found.append(index)
        vectors.append(as_vector(compute_features(built.inputs)))
        labels.append(built.p_with)
        bases.append(built.p_without)
        base = prepare(profile) if variant != Variant() else known
        changed.append(known["rows"] != base["rows"] or known["items"] != base["items"])
    return VariantRun(
        tuple(found), np.array(vectors), np.array(labels), locked, tuple(changed), np.array(bases)
    )


def evaluate_variant(
    params: Params,
    master_seed: int,
    indices: Sequence[int],
    variant: Variant,
    predict: Callable[[np.ndarray], np.ndarray],
    forecaster: Forecaster,
    paths: int,
) -> dict[str, Any]:
    return run_variant(params, master_seed, indices, variant, forecaster, paths).summary(predict)


def live_state(forecaster: Forecaster, labels_path: Path) -> dict[str, Any]:
    """What the code and files on this machine are NOW, to compare with what the labels recorded."""
    return {
        "label_version": LABEL_VERSION,
        "horizon_max_weeks": RISK_CHECK_MAX_WEEKS,
        "served_model_files": served_model_files(forecaster),
        "labels_sha256": sha256_file(labels_path),
    }


def check_provenance(
    manifest: dict[str, Any], results: dict[str, Any], params: Params, live: dict[str, Any]
) -> None:
    """Refuse to stress a model against labels or code it was not made with."""
    if manifest["params_hash"] != params.hash():
        raise ValueError("the labels were made with different generator parameters")
    if manifest["feature_schema_hash"] != FEATURE_SCHEMA_HASH:
        raise ValueError("the labels were made with a different feature schema")
    if manifest["label_version"] != live["label_version"]:
        raise ValueError("the labels were made under a different label version")
    if manifest["horizon_max_weeks"] != live["horizon_max_weeks"]:
        raise ValueError("the labels were made with a different simulation horizon")
    if manifest["served_model_files"] != live["served_model_files"]:
        raise ValueError("the labels were made with a different served model")
    if manifest["file"]["sha256"] != results["labels_sha256"]:
        raise ValueError("the stored run was trained on different labels than the manifest names")
    if live["labels_sha256"] != manifest["file"]["sha256"]:
        raise ValueError("the labels file has changed since its manifest was written")


def run(config_name: str, out: Path, paths: int | None = None, limit: int | None = None) -> dict:
    run_dir = RUNS_DIR / config_name
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    manifest = json.loads((LABELS_PATH.parent / MANIFEST_FILE).read_text(encoding="utf-8"))
    params = load_params()
    forecaster = served_forecaster()
    check_provenance(manifest, results, params, live_state(forecaster, LABELS_PATH))
    paths = paths or int(manifest["paths"])
    master_seed = int(manifest["seed"])
    model, calibrator = load_run(run_dir)
    two_part = bool(getattr(model, "two_part", False))

    def predict(x: np.ndarray) -> np.ndarray:
        return calibrated_predict(model, calibrator, x)

    labels = load_labels(LABELS_PATH)
    _, lockbox = split_lockbox(labels.with_base() if two_part else labels)
    indices = [int(i) for i in lockbox.index][:limit]
    runs = {
        name: run_variant(params, master_seed, indices, variant, forecaster, paths)
        for name, variant in VARIANTS.items()
    }
    stored_labels = dict(zip(lockbox.index.tolist(), lockbox.y.tolist(), strict=True))
    identity = runs["identity"]
    report = {
        "model": results["winner"],
        "calibration": results["calibration"]["chosen"],
        "lockbox_profiles": len(indices),
        "paths": paths,
        "master_seed": master_seed,
        "stored_labels": {
            "profiles": len(lockbox),
            "brier": brier(predict(lockbox.x), lockbox.y),
            "mean_prediction": float(predict(lockbox.x).mean()),
            "mean_label": float(lockbox.y.mean()),
        },
        "identity_reproduces_stored_labels_max_abs_diff": float(
            max(
                (
                    abs(label - stored_labels[i])
                    for i, label in zip(identity.indices, identity.labels, strict=True)
                ),
                default=0.0,
            )
        ),
        "variants": {name: r.summary(predict, two_part) for name, r in runs.items()},
        "mean_abs_label_shift_vs_identity": {
            name: _shift(identity, r) for name, r in runs.items() if name != "identity"
        },
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "stress.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return report


def _shift(identity: VariantRun, other: VariantRun) -> float | None:
    """Mean absolute change of the simulated label, over the profiles present in both runs."""
    base = dict(zip(identity.indices, identity.labels, strict=True))
    diffs = [abs(label - base[i]) for i, label in zip(other.indices, other.labels, strict=True)
             if i in base]  # fmt: skip
    return float(np.mean(diffs)) if diffs else None


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Stress-test the trained Engine 2 model.")
    parser.add_argument("--config", default="full")
    parser.add_argument("--paths", type=int, default=None, help="default: the labels' own count")
    parser.add_argument("--limit", type=int, default=None, help="score only the first N lockbox")
    args = parser.parse_args(argv)
    report = run(args.config, RUNS_DIR / args.config, args.paths, args.limit)
    for name, row in report["variants"].items():
        print(f"{name}: {row}")  # noqa: T201


if __name__ == "__main__":
    main()
