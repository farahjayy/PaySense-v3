"""A population record of forecast errors for users with a short history (engine v3, ADR D-61, F2).

A user with fewer than about six months of complete weeks has too few past origins for their own
error record to show how far the forecast can drift: widening it (D-54) could not bring the band
near 80% for 17-25 weeks of history. Below the band rule's `below_weeks` the error record is
instead a pooled set of 13-week error paths measured on synthetic development students with that
much history, each path written as a RATIO of the student's recent level, and multiplied by the
user's own recent level. Only the level is the user's; the shape of the uncertainty is the
population's.

The record is fitted by `ml/engine1_eval/band_v3.py`, written to `models/engine1/`, and named with
its SHA-256 in the band rule file. It is refused when its digest differs, and Engine 2 records the
digest, so a different record stops the risk model from serving (D-40).
"""

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

KINDS = ("spend", "income")
HORIZON_WEEKS = 13  # the length of a population error path: the LSTM's own horizon
LEVEL_WEEKS = (
    26  # the recent level is the mean of this many latest weeks (all of a shorter history)
)
DECIMALS = 4


class PopulationError(RuntimeError):
    """The population record is missing, malformed or not the one the band rule names."""


@dataclass(frozen=True, eq=False)
class PopulationRecord:
    paths: dict[str, np.ndarray]  # kind -> (paths, HORIZON_WEEKS) ratio errors


def recent_level(values: np.ndarray, weeks: int = LEVEL_WEEKS) -> float:
    values = np.asarray(values, dtype=float)
    return float(values[-weeks:].mean()) if len(values) else 0.0


def digest(path: Path) -> str:
    """SHA-256 of the file with LF line endings (ADR D-52)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _parse(data: dict[str, Any]) -> PopulationRecord:
    try:
        paths = {kind: np.asarray(data["kinds"][kind], dtype=float) for kind in KINDS}
    except (KeyError, TypeError, ValueError) as err:
        raise PopulationError(f"the population record is malformed: {err!r}") from err
    for kind, array in paths.items():
        if array.ndim != 2 or len(array) == 0 or not np.isfinite(array).all():
            raise PopulationError(f"the population record holds no usable {kind} paths")
    return PopulationRecord(paths)


@lru_cache(maxsize=8)
def load_population(path: Path, expected_sha256: str) -> PopulationRecord:
    try:
        found = digest(path)
    except OSError as err:
        raise PopulationError(f"cannot read the population record at {path}: {err}") from err
    if found != expected_sha256:
        raise PopulationError(
            f"the population record's digest {found[:12]} is not the {expected_sha256[:12]} the "
            "band rule names; refit both together"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as err:
        raise PopulationError(f"the population record at {path} is not JSON: {err}") from err
    return _parse(data)


def write_population(
    path: Path, paths: dict[str, Any], provenance: dict[str, Any]
) -> dict[str, Any]:
    """Write the record (paths rounded to `DECIMALS`) and return what was written."""
    record = {
        "version": "1",
        "horizon_weeks": HORIZON_WEEKS,
        "level_weeks": LEVEL_WEEKS,
        "unit": "error / recent level (mean of the latest 26 weeks, all of a shorter history)",
        "kinds": {
            kind: [[round(float(v), DECIMALS) for v in row] for row in paths[kind]]
            for kind in KINDS
        },
        "fitted_on": provenance,
        "generated_by": "python -m ml.engine1_eval.band_v3",
    }
    _parse(record)  # never write what the loader would refuse
    path.write_text(
        json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n"
    )
    return record


def scaled_paths(record: PopulationRecord, kind: str, level: float) -> np.ndarray:
    """The population's ratio paths in the user's own units."""
    return record.paths[kind] * level
