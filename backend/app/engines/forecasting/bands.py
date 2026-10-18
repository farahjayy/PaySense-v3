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

from app.engines.forecasting.simulate import CLIP_MODES

BAND_FILE = Path(__file__).resolve().parents[3] / "models" / "engine1" / "band_inflation.json"
KINDS = ("spend", "income")
MIN_POPULATION_BELOW = 18  # a population record must cover at least the first bucket (17 weeks)


class BandRuleError(RuntimeError):
    """The band table is missing or malformed."""


@dataclass(frozen=True)
class Bucket:
    min_weeks: int
    spend: float
    income: float


@dataclass(frozen=True)
class PopulationRef:
    """Which population error record a short history uses (engine v3, D-61), and below how many
    weeks of history. The file sits next to the band rule and must have this digest."""

    file: str
    sha256: str
    below_weeks: int


@dataclass(frozen=True)
class BandRule:
    version: str
    buckets: tuple[Bucket, ...]  # ascending by min_weeks; the first starts at the forecast gate
    clip: str = "week"  # where simulated spending and income are floored at zero (D-60)
    population: PopulationRef | None = None
    folder: Path | None = None  # where the rule file lives (for the population record)

    def population_path(self) -> Path | None:
        if self.population is None:
            return None
        return (self.folder or BAND_FILE.parent) / self.population.file

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
    clip = data.get("clip", "week")
    if clip not in CLIP_MODES:
        raise BandRuleError(f"the band rule's clip must be one of {CLIP_MODES}, got {clip!r}")
    return BandRule(version, buckets, clip, _population(data.get("population_record")))


def _population(data: Any) -> PopulationRef | None:
    if data is None:
        return None
    try:
        ref = PopulationRef(str(data["file"]), str(data["sha256"]), int(data["below_weeks"]))
    except (KeyError, TypeError, ValueError) as err:
        raise BandRuleError(f"the population record reference is malformed: {err!r}") from err
    plain = (
        Path(ref.file).name == ref.file and ref.file not in {"", ".", ".."} and "\\" not in ref.file
    )
    if not plain:
        raise BandRuleError(f"the population record {ref.file!r} is not a plain file name")
    if len(ref.sha256) != 64:
        raise BandRuleError("the population record reference needs a SHA-256 digest")
    if ref.below_weeks < MIN_POPULATION_BELOW:
        raise BandRuleError("a population record must cover at least the shortest histories")
    return ref


def text_digest(path: Path) -> str:
    """SHA-256 of the file with LF line endings (ADR D-52: line endings are not settings)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@lru_cache(maxsize=4)
def load_band_rule(path: Path = BAND_FILE) -> BandRule:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise BandRuleError(f"cannot read the band table at {path}: {err}") from err
    rule = parse_rule(data)
    return BandRule(rule.version, rule.buckets, rule.clip, rule.population, path.parent)


def inflation_for(weeks: int, kind: str) -> float:
    """The widening factor for a user with `weeks` complete weeks of history."""
    return load_band_rule().factor(weeks, kind)
