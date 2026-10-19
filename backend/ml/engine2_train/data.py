"""Reading the label file into arrays (plan P5, task D6).

`load_labels` never reads the generator's answer keys (`truth`). The analysis helpers in
`report.py` do, for description only.
"""

import json
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from app.engines.risk.features import FEATURE_NAMES

LABELS_PATH = Path(__file__).resolve().parents[3] / "data" / "engine2" / "labels.jsonl"
N_STRATA = 10  # quantile bins of the soft label; ties at exactly 0 or 1 collapse some of them
LOCKBOX_EVERY = 10  # every tenth profile is set aside, untouched until the final score (H5/H6)
# Engine v3 (plan 2026-10-18-engine-v3 §5.2): profiles from this index on are the NEW lockbox. When
# a label file holds them, the old every-tenth lockbox below it is kept out of training as well
# and scored only as continuity (its third scoring, disclosed).
NEW_LOCKBOX_FROM = 10_000
# The two-part target (D-62) carries the simulated chance without the purchase as an extra last
# column: it is never a feature (no model sees it), it is the base the prediction is composed on.
BASE_COLUMN = "p_without (two-part base, not a feature)"
LOW_BASELINE = "low_baseline"
LOW_BASELINE_BELOW = 0.10  # P(shortfall) without the purchase below the Safe edge


@dataclass(frozen=True)
class Dataset:
    x: np.ndarray  # (profiles, features) in FEATURE_NAMES order
    y: np.ndarray  # the soft label: simulated probability of a shortfall with the plan
    index: np.ndarray  # profile indices
    names: tuple[str, ...]
    # by-products of the label run, kept for analysis (never features)
    p_without: np.ndarray | None = None  # the same simulation without the purchase
    capped: np.ndarray | None = None  # the horizon was cut short
    label_monthly: np.ndarray | None = None  # per-month shortfall definition (sensitivity)

    def __len__(self) -> int:
        return len(self.y)

    def take(self, mask: np.ndarray) -> "Dataset":
        """The rows where `mask` is true, every array kept aligned."""

        def pick(a: np.ndarray | None) -> np.ndarray | None:
            return None if a is None else a[mask]

        return Dataset(
            self.x[mask], self.y[mask], self.index[mask], self.names,
            pick(self.p_without), pick(self.capped), pick(self.label_monthly),
        )  # fmt: skip

    def with_base(self) -> "Dataset":
        """The same rows with `p_without` as an extra last column named `BASE_COLUMN`."""
        if self.p_without is None:
            raise ValueError("the two-part target needs p_without for every profile")
        if self.names and self.names[-1] == BASE_COLUMN:
            return self
        return replace(
            self,
            x=np.column_stack([self.x, self.p_without]),
            names=(*self.names, BASE_COLUMN),
        )

    def subset(self, columns: tuple[str, ...]) -> "Dataset":
        positions = [self.names.index(c) for c in columns]
        return replace(self, x=self.x[:, positions], names=columns)

    def strata(self) -> np.ndarray:
        """Quantile bins of the soft label: the stratification variable for cross-validation."""
        edges = np.quantile(self.y, np.linspace(0, 1, N_STRATA + 1)[1:-1])
        return np.searchsorted(edges, self.y, side="right")

    @property
    def n_strata(self) -> int:
        """How many distinct bins there really are (fewer than `N_STRATA` when labels tie)."""
        return int(len(np.unique(self.strata())))

    def subgroups(self) -> dict[str, np.ndarray]:
        """Row masks scored separately: where the plan, not the baseline, decides the band."""
        if self.p_without is None:
            return {}
        return {LOW_BASELINE: self.p_without < LOW_BASELINE_BELOW}


def _has_new_lockbox(data: Dataset) -> bool:
    return bool(np.any(data.index >= NEW_LOCKBOX_FROM))


def split_lockbox(data: Dataset) -> tuple[Dataset, Dataset]:
    """(development, lockbox). The lockbox is excluded from CV, model choice, tuning, calibration
    and the ablation; the final model is scored on it exactly once. With profiles from
    `NEW_LOCKBOX_FROM` on, those are the lockbox and the old every-tenth lockbox is excluded from
    development too (`continuity_lockbox`)."""
    old = data.index % LOCKBOX_EVERY == 0
    if _has_new_lockbox(data):
        new = data.index >= NEW_LOCKBOX_FROM
        return data.take(~new & ~old), data.take(new)
    return data.take(~old), data.take(old)


def continuity_lockbox(data: Dataset) -> Dataset:
    """The old every-tenth lockbox when a new lockbox exists (scored only for continuity), else
    no rows."""
    if not _has_new_lockbox(data):
        return data.take(np.zeros(len(data), dtype=bool))
    return data.take((data.index < NEW_LOCKBOX_FROM) & (data.index % LOCKBOX_EVERY == 0))


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
        p_without=_column(rows, "p_without"),
        capped=_column(rows, "horizon_capped", bool),
        label_monthly=_column(rows, "label_monthly"),
    )


def _column(rows: list[dict], key: str, dtype=float) -> np.ndarray | None:
    """A by-product column, or None when the file does not carry it (an older label file)."""
    if any(key not in r for r in rows):
        return None
    return np.array([r[key] for r in rows], dtype=dtype)
