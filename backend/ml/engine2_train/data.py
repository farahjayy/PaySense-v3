"""Reading the label file into arrays (plan P5, task D6)."""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.engines.risk.features import FEATURE_NAMES

LABELS_PATH = Path(__file__).resolve().parents[3] / "data" / "engine2" / "labels.jsonl"
N_STRATA = 10


@dataclass(frozen=True)
class Dataset:
    x: np.ndarray  # (profiles, features) in FEATURE_NAMES order
    y: np.ndarray  # the soft label: simulated probability of a shortfall with the plan
    index: np.ndarray  # profile indices
    names: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.y)

    def subset(self, columns: tuple[str, ...]) -> "Dataset":
        positions = [self.names.index(c) for c in columns]
        return Dataset(self.x[:, positions], self.y, self.index, columns)

    def strata(self) -> np.ndarray:
        """Deciles of the soft label: the stratification variable for cross-validation."""
        edges = np.quantile(self.y, np.linspace(0, 1, N_STRATA + 1)[1:-1])
        return np.searchsorted(edges, self.y, side="right")


def load_labels(path: Path = LABELS_PATH) -> Dataset:
    """Features and soft labels of every profile that was not locked. Reads no answer key."""
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if not record["locked"]:
                rows.append(record)
    if not rows:
        raise ValueError(f"no labelled profiles in {path}")
    return Dataset(
        x=np.array([[r["features"][name] for name in FEATURE_NAMES] for r in rows], dtype=float),
        y=np.array([r["label"] for r in rows], dtype=float),
        index=np.array([r["index"] for r in rows], dtype=int),
        names=FEATURE_NAMES,
    )
