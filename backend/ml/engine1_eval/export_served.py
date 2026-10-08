"""Train the evaluated LSTM recipe and export it for serving (plan P4, task C6):

    cd backend && uv run python -m ml.engine1_eval.export_served

The recipe is exactly the one the P3 evaluation scored (same config, same seed, same training
profiles and cutoff), so the served network is the evaluated network. The result is a pair of ONNX
files (spend, income) and `metadata.json` under `backend/models/engine1/<version>/`, with a parity
check against torch on real windows from profiles the network never trained on.
"""

import argparse
import hashlib
import json
import platform
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

import numpy as np
import onnxruntime
import torch

from ml.engine1_eval.models.lstm import EPS, build_windows
from ml.engine1_eval.run import KINDS, DataPaths, _synthetic_series, _train_lstms, load_config

MODELS_DIR = Path(__file__).resolve().parents[2] / "models" / "engine1"
SELECTION = Path(__file__).resolve().parents[3] / "reports" / "engine1" / "selection.json"
PARITY_WINDOWS = 400
PARITY_TOLERANCE = 1e-4  # in scaled units: windows are divided by their own mean


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(config_name: str, version: str, out_dir: Path | None = None) -> dict:
    config = load_config(config_name)
    paths = DataPaths()
    train, test_pairs = _synthetic_series(config, paths)
    cutoff = train[0].start + timedelta(weeks=config.synthetic["cutoff_week"])
    models = _train_lstms(config, train, until=cutoff)
    target = (out_dir or MODELS_DIR) / version
    target.mkdir(parents=True, exist_ok=True)

    holdout = [pair[kind] for pair in test_pairs for kind in KINDS]
    parity = {}
    for kind, model in models.items():
        file = target / f"lstm_{kind}.onnx"
        model.to_onnx(file)
        session = onnxruntime.InferenceSession(str(file), providers=["CPUExecutionProvider"])
        windows, _ = build_windows([s for s in holdout if s.kind == kind], model.config, until=None)
        windows = windows[:PARITY_WINDOWS]
        expected = model.predict_ratio(windows)
        actual = session.run(None, {"window": windows.reshape(len(windows), -1, 1)})[0]
        parity[kind] = {
            "windows": int(len(windows)),
            "max_abs_difference": float(np.max(np.abs(expected - actual))),
        }
        if parity[kind]["max_abs_difference"] > PARITY_TOLERANCE:
            raise RuntimeError(f"ONNX output for {kind} differs from torch: {parity[kind]}")

    first = next(iter(models.values())).config
    metadata = {
        "model": "global-lstm",
        "version": version,
        "kinds": list(KINDS),
        "window": first.window,
        "horizon": first.horizon,
        "hidden": first.hidden,
        "epsilon": EPS,
        "training": {
            "config": config_name,
            "seed": config.seed,
            "profiles": len(train) // len(KINDS),
            "cutoff_week": config.synthetic["cutoff_week"],
            "series_start": train[0].start.isoformat(),
            "lstm": config.lstm,
        },
        "parameters": {kind: m.parameter_count for kind, m in models.items()},
        "parity_with_torch": parity,
        "selection_sha256": _sha256(SELECTION) if SELECTION.exists() else None,
        "files": {f"lstm_{kind}.onnx": _sha256(target / f"lstm_{kind}.onnx") for kind in KINDS},
        "versions": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "onnxruntime": onnxruntime.__version__,
            "numpy": np.__version__,
        },
    }
    (target / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return metadata


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export the served Engine 1 LSTM to ONNX.")
    parser.add_argument("--config", default="full")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    metadata = export(args.config, args.version, args.out)
    print(f"exported {metadata['version']}: parity {metadata['parity_with_torch']}")  # noqa: T201


if __name__ == "__main__":
    main()
