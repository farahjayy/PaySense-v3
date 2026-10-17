"""How much a user's own error record is widened before it is resampled (WP16, change C2).

A short history understates future uncertainty: its error record cannot show a level that drifts
further than it has so far. v2 of the engines widened every record by one factor (1.5), and the
80% band still held the real outcome only 46-69% of the time. v3 widens by a small table of
factors that depends on how many weeks of history the user has and on the series (spending or
income). The table is fitted by `ml/engine1_eval/band_calibration.py` on synthetic students that
neither the forecast network nor Engine 2's lockbox ever saw, written to `band_inflation.json`
with its provenance, and checked on the held-out Engine 1 test students
(`reports/engine1/band_calibration.md`). Engine 2's labels are made with it, so its digest is
recorded in the risk model and a changed table stops the model from serving.
"""

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

BAND_FILE = Path(__file__).resolve().parents[3] / "models" / "engine1" / "band_inflation.json"
KINDS = ("spend", "income")


class BandRuleError(RuntimeError):
    """The band table is missing or malformed."""


@dataclass(frozen=True)
class Bucket:
    min_weeks: int
    spend: float
    income: float


@dataclass(frozen=True)
class BandRule:
    version: str
    buckets: tuple[Bucket, ...]  # ascending by min_weeks; the first starts at the forecast gate

    def factor(self, weeks: int, kind: str) -> float:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
        chosen = self.buckets[0]
        for bucket in self.buckets:
            if weeks >= bucket.min_weeks:
                chosen = bucket
        return float(getattr(chosen, kind))


def parse_rule(data: dict[str, Any]) -> BandRule:
    try:
        buckets = tuple(
            Bucket(int(b["min_weeks"]), float(b["spend"]), float(b["income"]))
            for b in data["buckets"]
        )
        version = str(data["version"])
    except (KeyError, TypeError, ValueError) as err:
        raise BandRuleError(f"the band table is malformed: {err!r}") from err
    if not buckets or [b.min_weeks for b in buckets] != sorted({b.min_weeks for b in buckets}):
        raise BandRuleError("band buckets must be non-empty and strictly ascending by min_weeks")
    if any(min(b.spend, b.income) < 1.0 for b in buckets):
        raise BandRuleError("a band factor below 1 would narrow the user's own error record")
    return BandRule(version, buckets)


def text_digest(path: Path) -> str:
    """SHA-256 of the file with LF line endings (ADR D-52: line endings are not settings)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@lru_cache(maxsize=4)
def load_band_rule(path: Path = BAND_FILE) -> BandRule:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise BandRuleError(f"cannot read the band table at {path}: {err}") from err
    return parse_rule(data)


def inflation_for(weeks: int, kind: str) -> float:
    """The widening factor for a user with `weeks` complete weeks of history."""
    return load_band_rule().factor(weeks, kind)
