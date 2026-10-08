"""The served global LSTM, run with ONNX Runtime (plan P4, task C6; ADR D-34).

The network was trained and exported offline (`ml/engine1_eval/export_served.py`); this class only
replays it, so torch never enters the API process (D-15). One network per series kind. Each input
window is the last `window` weeks divided by their own mean and the output is multiplied back, the
same scaling used in training. Beyond the trained horizon the forecast is continued recursively
(the network is fed its own forecast): that extension was not part of the evaluation.
"""

import json
from datetime import date
from pathlib import Path

import numpy as np
import onnxruntime

KINDS = ("spend", "income")
MODEL_DIR = Path(__file__).resolve().parents[3] / "models" / "engine1"


class OnnxLstm:
    """One kind's network as a forecaster."""

    def __init__(self, path: Path, window: int, horizon: int, epsilon: float) -> None:
        self.name = "lstm"
        self.window, self.horizon, self._epsilon = window, horizon, epsilon
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 1  # one tiny network: threads would cost more than they save
        self._session = onnxruntime.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )

    def _context(self, history: np.ndarray) -> np.ndarray:
        tail = np.asarray(history[-self.window :], dtype=float)
        if len(tail) < self.window:  # a short history is left-padded with its own mean
            tail = np.concatenate([np.full(self.window - len(tail), tail.mean()), tail])
        return tail

    def _one_block(self, history: np.ndarray) -> np.ndarray:
        context = self._context(history)
        mean = float(context.mean())
        if mean <= self._epsilon:
            return np.zeros(self.horizon)
        x = (context / mean).astype(np.float32).reshape(1, -1, 1)
        ratio = self._session.run(None, {"window": x})[0][0]
        return np.clip(ratio.astype(float) * mean, 0.0, None)

    def forecast(self, history: np.ndarray, horizon: int, start: date) -> np.ndarray:
        if len(history) == 0:
            raise ValueError("a forecast needs at least one week of history")
        extended = np.asarray(history, dtype=float)
        blocks: list[np.ndarray] = []
        while sum(len(b) for b in blocks) < horizon:
            block = self._one_block(extended)
            blocks.append(block)
            extended = np.concatenate([extended, block])
        return np.concatenate(blocks)[:horizon]


class ServedLstm:
    """Both kinds' networks. `for_kind` gives the forecaster for one series."""

    name = "lstm"

    def __init__(self, directory: Path) -> None:
        meta = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        self.metadata = meta
        self._models = {
            kind: OnnxLstm(
                directory / f"lstm_{kind}.onnx", meta["window"], meta["horizon"], meta["epsilon"]
            )
            for kind in meta["kinds"]
        }

    def for_kind(self, kind: str) -> OnnxLstm:
        return self._models[kind]

    def forecast(self, history: np.ndarray, horizon: int, start: date) -> np.ndarray:
        raise TypeError("the LSTM is per kind: use for_kind('spend') or for_kind('income')")


def load_served(version: str = "v1") -> ServedLstm:
    return ServedLstm(MODEL_DIR / version)
