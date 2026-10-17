"""Export the trained Engine 2 winner as a servable artefact (plan P5 D8 / P6 E1).

    cd backend && uv run python -m ml.engine2_train.export [--run runs/full] [--version v1]

Writes `backend/models/engine2/<version>/model.onnx` and `metadata.json`. The model is converted
to ONNX (no pickle, and the API needs only onnxruntime). The metadata carries the calibrator as
plain numbers, the reference student used to explain a result (the median development profile),
and everything the labels were built against, so the server can refuse a model that no longer
matches the code. The export checks itself: ONNX against the original model on held-out rows, and
the loaded predictor against the training-side calibrated prediction, and records both.
"""

import argparse
import hashlib
import json
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import onnxruntime
from onnxmltools import convert_lightgbm, convert_xgboost
from onnxmltools.convert.common.data_types import FloatTensorType
from skl2onnx import to_onnx

from app.engines.forecasting.onnx_model import MODEL_DIR as ENGINE1_DIR
from app.engines.forecasting.serving import ARTEFACT_VERSION as ENGINE1_VERSION
from app.engines.forecasting.serving import SERVED_MODEL
from app.engines.forecasting.simulate import SAFE_BELOW
from app.engines.risk.artefact import MODEL_ROOT, load_engine2
from app.engines.risk.features import FEATURE_NAMES, FEATURE_SCHEMA_HASH
from ml.engine2_train.calibrate import Calibrator
from ml.engine2_train.data import LABELS_PATH, load_labels, split_lockbox
from ml.engine2_train.metrics import EPS
from ml.engine2_train.train import RUNS_DIR

PARITY_SAMPLE = 2000
MIN_REFERENCE_PROFILES = 100
LOOSE_TOLERANCE = 1e-3  # a feature within float32 rounding of a split can flip one tree
# A row further off than LOOSE_TOLERANCE is accepted only when a split is PROVEN to go the other way
# because ONNX stores the threshold as float32 (WP16), and never by more than this.
MAX_FLIP_DIFF = 1e-2


class ExportError(RuntimeError):
    """The model cannot be exported as it stands; nothing was written to the output folder."""


def within_tolerance(diff: np.ndarray) -> bool:
    """True only if every difference is a finite number no larger than the tolerance (NaN fails)."""
    return bool(np.isfinite(diff).all() and diff.max() <= LOOSE_TOLERANCE)


def float32_split_flips(
    dump: dict[str, Any], row: np.ndarray, names: Sequence[str]
) -> list[tuple[str, float, float]]:
    """Splits of a LightGBM model dump that send `row` the other way once the threshold and the
    value are stored as float32 (what ONNX Runtime evaluates): (feature, value, threshold)."""
    flips: list[tuple[str, float, float]] = []

    def walk(node: dict[str, Any]) -> None:
        if "split_feature" not in node:
            return
        feature, threshold = int(node["split_feature"]), float(node["threshold"])
        value = float(row[feature])
        exact = value <= threshold
        stored = float(np.float32(value)) <= float(np.float32(threshold))
        if exact != stored:
            flips.append((names[feature], value, threshold))
        walk(node["left_child"])
        walk(node["right_child"])

    for tree in dump.get("tree_info", []):
        walk(tree["tree_structure"])
    return flips


def accept_parity(diff: np.ndarray, explained: np.ndarray) -> bool:
    """Every difference finite; any beyond LOOSE_TOLERANCE explained by a float32 split flip and
    no larger than MAX_FLIP_DIFF."""
    if not np.isfinite(diff).all():
        return False
    over = diff > LOOSE_TOLERANCE
    return bool(np.all(explained[over]) and np.all(diff[over] <= MAX_FLIP_DIFF))


def reference_student(development: Any) -> tuple[dict[str, float], int]:
    """The median, feature by feature, of the development profiles labelled Safe, and how many."""
    safe = development.y < SAFE_BELOW
    count = int(safe.sum())
    if count < MIN_REFERENCE_PROFILES:
        raise ExportError("too few Safe development profiles to define a reference student")
    medians = np.median(development.x[safe], axis=0)
    return {name: float(v) for name, v in zip(FEATURE_NAMES, medians, strict=True)}, count


def convert(fitted: Any, n_features: int) -> bytes:
    """The fitted model as ONNX bytes; the output named 'probabilities' (or last) is P(class 1)."""
    if fitted.name == "lightgbm":
        types = [("input", FloatTensorType([None, n_features]))]
        return convert_lightgbm(fitted.model, initial_types=types, zipmap=False).SerializeToString()
    if fitted.name == "xgboost":
        types = [("input", FloatTensorType([None, n_features]))]
        return convert_xgboost(fitted.model, initial_types=types).SerializeToString()
    sample = np.zeros((1, n_features), dtype=np.float32)
    return to_onnx(fitted.model, sample, options={"zipmap": False}).SerializeToString()


def _raw_probability(onnx_bytes: bytes, x: np.ndarray) -> np.ndarray:
    session = onnxruntime.InferenceSession(onnx_bytes, providers=["CPUExecutionProvider"])
    names = [o.name for o in session.get_outputs()]
    output = "probabilities" if "probabilities" in names else names[-1]
    out = session.run([output], {session.get_inputs()[0].name: x.astype(np.float32)})[0]
    return np.asarray(out, dtype=float)[:, 1]


def parity(fitted: Any, onnx_bytes: bytes, x: np.ndarray) -> dict[str, float | int]:
    """How far ONNX Runtime is from the original model on these rows."""
    diff = np.abs(_raw_probability(onnx_bytes, x) - fitted.predict(x))
    return {
        "rows": int(len(x)),
        "max_abs_diff": float(diff.max()),
        "rows_over_1e-6": int((diff > 1e-6).sum()),
    }


def _write_metadata(folder: Path, metadata: dict[str, Any]) -> None:
    (folder / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def export(
    run_dir: Path,
    out_dir: Path,
    labels_path: Path = LABELS_PATH,
    version: str = "v1",
) -> dict[str, Any]:
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    if results["feature_schema_hash"] != FEATURE_SCHEMA_HASH:
        raise ExportError("the run was made for a different feature schema than this code")
    fitted = joblib.load(run_dir / "final_model.joblib")
    calibrator = json.loads((run_dir / "calibrator.json").read_text(encoding="utf-8"))
    data = load_labels(labels_path)
    development, lockbox = split_lockbox(data)

    reference, safe_count = reference_student(development)

    onnx_bytes = convert(fitted, len(FEATURE_NAMES))
    checked = np.vstack([lockbox.x, development.x[:PARITY_SAMPLE]])
    model_parity = parity(fitted, onnx_bytes, checked)
    diff = np.abs(_raw_probability(onnx_bytes, checked) - fitted.predict(checked))
    explained = np.zeros(len(diff), dtype=bool)
    flips: list[dict[str, Any]] = []
    booster = getattr(fitted.model, "booster_", None)
    if booster is not None:
        dump = booster.dump_model()
        for row in np.flatnonzero(diff > LOOSE_TOLERANCE):
            found = float32_split_flips(dump, checked[row], FEATURE_NAMES)
            explained[row] = bool(found)
            flips += [
                {
                    "row": int(row),
                    "feature": f,
                    "value": v,
                    "threshold": t,
                    "diff": float(diff[row]),
                }
                for f, v, t in found
            ]
    if not accept_parity(diff, explained):
        raise ExportError(f"ONNX output differs from the trained model: {model_parity}")
    model_parity["explained_by_float32_thresholds"] = flips

    metadata = {
        "version": version,
        "family": fitted.name,
        "feature_names": list(FEATURE_NAMES),
        "feature_schema_hash": FEATURE_SCHEMA_HASH,
        "onnx_sha256": hashlib.sha256(onnx_bytes).hexdigest(),
        "calibrator": calibrator,
        "logit_eps": EPS,
        "baseline": reference,
        "baseline_profiles": safe_count,
        "explanation": {
            "method": "baseline_shapley",
            "reference": (
                "the median, feature by feature, of the development profiles whose label is Safe "
                "(below 0.10): a typical student who is not at risk (ADR D-40)"
            ),
        },
        "monotone_constraints": results["served_model_has_monotone_constraints"],
        "label": {
            "label_version": results["labels_manifest"]["label_version"],
            "horizon_max_weeks": results["labels_manifest"]["horizon_max_weeks"],
            "paths": results["labels_manifest"]["paths"],
            "seed": results["labels_manifest"]["seed"],
            "served_model_files": results["labels_manifest"]["served_model_files"],
            "served_model": SERVED_MODEL,
            # LF form, so the digest does not depend on the checkout's line endings
            "engine1_metadata_sha256": hashlib.sha256(
                (ENGINE1_DIR / ENGINE1_VERSION / "metadata.json")
                .read_bytes()
                .replace(b"\r\n", b"\n")
            ).hexdigest(),
        },
        "serving_constants": results["serving_constants"],
        "training": {
            "config": results["config"]["name"],
            "git_commit": results["git_commit"],
            "labels_sha256": results["labels_sha256"],
            "development_profiles": results["development_profiles"],
            "lockbox_profiles": results["lockbox_profiles"],
            "final_params": results["final_params"],
            "versions": results["versions"],
        },
        "metrics": {
            "cv_brier": results["models"][fitted.name]["brier_mean"],
            "constant_baseline_brier": results["constant_baseline_brier"],
            "lockbox_calibrated": results["lockbox"]["calibrated"],
            "lockbox_raw": results["lockbox"]["raw"],
            "lockbox_logistic_brier": results["lockbox"]["logistic_benchmark_brier"],
            "lockbox_constant_brier": results["lockbox"]["constant_brier"],
            "lockbox_band_agreement": results["lockbox"]["band_agreement"],
        },
        "parity": {"onnx_vs_trained_model": model_parity},
    }
    # Everything is written and checked in a scratch folder; the output folder is only touched once
    # the artefact has passed, so a failed export never leaves an unverified model where a server
    # could load it, nor destroys the good one that was there.
    staging = Path(tempfile.mkdtemp(prefix="engine2-export-"))
    try:
        (staging / "model.onnx").write_bytes(onnx_bytes)
        _write_metadata(staging, metadata)
        # The loaded artefact, end to end, against the training-side calibrated prediction.
        predictor = load_engine2(staging)
        served = predictor.predict_batch(checked)
        trained = Calibrator.from_dict(calibrator).apply(fitted.predict(checked))
        end_to_end = np.abs(served - trained)
        if not accept_parity(end_to_end, explained):  # the same proven float32 flips only
            raise ExportError(f"the served artefact differs from the trained model: {end_to_end}")
        metadata["parity"]["served_vs_trained_calibrated"] = {
            "rows": int(len(checked)),
            "max_abs_diff": float(end_to_end.max()),
            "rows_over_1e-6": int((end_to_end > 1e-6).sum()),
        }
        _write_metadata(staging, metadata)
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging, out_dir)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return metadata


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Export the Engine 2 winner as a servable artefact."
    )
    parser.add_argument("--run", type=Path, default=RUNS_DIR / "full")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--labels", type=Path, default=LABELS_PATH)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    out = args.out or MODEL_ROOT / args.version
    try:
        metadata = export(args.run, out, args.labels, args.version)
    except ExportError as err:
        raise SystemExit(f"export refused: {err}") from err
    print(f"wrote {out} ({metadata['family']}, parity {metadata['parity']})")  # noqa: T201


if __name__ == "__main__":
    main()
