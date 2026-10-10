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


def export(
    run_dir: Path,
    out_dir: Path,
    labels_path: Path = LABELS_PATH,
    version: str = "v1",
) -> dict[str, Any]:
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    if results["feature_schema_hash"] != FEATURE_SCHEMA_HASH:
        raise SystemExit("the run was made for a different feature schema than this code")
    fitted = joblib.load(run_dir / "final_model.joblib")
    calibrator = json.loads((run_dir / "calibrator.json").read_text(encoding="utf-8"))
    data = load_labels(labels_path)
    development, lockbox = split_lockbox(data)

    safe = development.y < SAFE_BELOW
    if int(safe.sum()) < MIN_REFERENCE_PROFILES:
        raise SystemExit("too few Safe development profiles to define a reference student")
    reference = {
        name: float(value)
        for name, value in zip(FEATURE_NAMES, np.median(development.x[safe], axis=0), strict=True)
    }

    onnx_bytes = convert(fitted, len(FEATURE_NAMES))
    checked = np.vstack([lockbox.x, development.x[:PARITY_SAMPLE]])
    model_parity = parity(fitted, onnx_bytes, checked)
    if model_parity["max_abs_diff"] > LOOSE_TOLERANCE:
        raise SystemExit(f"ONNX output differs from the trained model: {model_parity}")

    metadata = {
        "version": version,
        "family": fitted.name,
        "feature_names": list(FEATURE_NAMES),
        "feature_schema_hash": FEATURE_SCHEMA_HASH,
        "onnx_sha256": hashlib.sha256(onnx_bytes).hexdigest(),
        "calibrator": calibrator,
        "logit_eps": EPS,
        "baseline": reference,
        "baseline_profiles": int(safe.sum()),
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
            "engine1_metadata_sha256": hashlib.sha256(
                (ENGINE1_DIR / ENGINE1_VERSION / "metadata.json").read_bytes()
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
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "model.onnx").write_bytes(onnx_bytes)
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )

    # The loaded artefact, end to end, against the training-side calibrated prediction.
    predictor = load_engine2(out_dir)
    served = predictor.predict_batch(checked)
    trained = Calibrator.from_dict(calibrator).apply(fitted.predict(checked))
    end_to_end = np.abs(served - trained)
    if end_to_end.max() > LOOSE_TOLERANCE:
        raise SystemExit(f"the served artefact differs from the trained model: {end_to_end.max()}")
    metadata["parity"]["served_vs_trained_calibrated"] = {
        "rows": int(len(checked)),
        "max_abs_diff": float(end_to_end.max()),
        "rows_over_1e-6": int((end_to_end > 1e-6).sum()),
    }
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
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
    metadata = export(args.run, out, args.labels, args.version)
    print(f"wrote {out} ({metadata['family']}, parity {metadata['parity']})")  # noqa: T201


if __name__ == "__main__":
    main()
