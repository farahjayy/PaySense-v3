"""Write the synthetic population to disk (plan P2, A11): `python -m ml.datagen.export`.

Two outputs, both streamed one profile at a time (nothing is held in memory):
  * `profiles.jsonl` - one full profile per line (transactions, plans, limits, the proposed
    purchase and the recurring ground truth): the Engine 2 input and the answer key for detection.
  * `weekly_series.csv` - one row per profile-week (discretionary spend and income): the Engine 1
    evaluation cohort. Only complete Monday-Sunday weeks inside the history are emitted.

`MANIFEST.json` records the seed, the parameter hash, counts, file hashes and package versions. It
carries no timestamp, so the same run reproduces it exactly.
"""

import argparse
import csv
import hashlib
import json
import platform
from collections.abc import Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from app.domain.categorize import REFUND, TRANSFER
from ml.datagen.calendar import week_start
from ml.datagen.params import Params, load_params
from ml.datagen.profile import StudentProfile, generate_profile

PROFILES_FILE = "profiles.jsonl"
COHORT_FILE = "weekly_series.csv"
MANIFEST_FILE = "MANIFEST.json"
COHORT_COLUMNS = ("profile_index", "persona", "week_start", "discretionary_sen", "income_sen")
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "synthetic"
DEFAULT_SEED = 20251228
DEFAULT_PROFILES = 10_000
HASH_CHUNK_BYTES = 1 << 20


@dataclass(frozen=True)
class WeekPoint:
    week_start: date
    discretionary_sen: int
    income_sen: int


def weekly_series(profile: StudentProfile) -> list[WeekPoint]:
    """Complete Monday-Sunday weeks only; refunds net against that week's spending."""
    first = week_start(profile.start)
    if first < profile.start:
        first += timedelta(days=7)
    last = week_start(profile.as_of)
    if last + timedelta(days=6) > profile.as_of:
        last -= timedelta(days=7)

    spend: dict[date, int] = {}
    income: dict[date, int] = {}
    for t in profile.discretionary_events:
        monday = week_start(t.date)
        if t.category == TRANSFER:
            continue
        sign = -1 if t.category == REFUND else 1
        spend[monday] = spend.get(monday, 0) + sign * t.amount_sen
    for t in profile.income_events:
        monday = week_start(t.date)
        income[monday] = income.get(monday, 0) + t.amount_sen

    points = []
    monday = first
    while monday <= last:
        points.append(WeekPoint(monday, max(spend.get(monday, 0), 0), income.get(monday, 0)))
        monday += timedelta(days=7)
    return points


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    return value


def profile_record(profile: StudentProfile) -> dict[str, Any]:
    return {
        "index": profile.index,
        "persona": profile.persona,
        "start": profile.start.isoformat(),
        "as_of": profile.as_of.isoformat(),
        "expected_monthly_income_sen": profile.expected_monthly_income_sen,
        "transactions": to_jsonable(profile.transactions),
        "plans": to_jsonable(profile.bnpl.plans),
        "limits": to_jsonable(profile.bnpl.limits),
        "actual_limits": to_jsonable(profile.bnpl.actual_limits),
        "purchase": to_jsonable(profile.purchase),
        "recurring_truth": to_jsonable(profile.recurring_truth),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def export_synthetic(params: Params, seed: int, count: int, out_dir: Path) -> dict[str, Any]:
    if count < 1:
        raise ValueError("count must be at least 1")
    out_dir.mkdir(parents=True, exist_ok=True)
    persona_counts: dict[str, int] = {}
    cohort_rows = 0
    with (
        (out_dir / PROFILES_FILE).open("w", encoding="utf-8", newline="\n") as profiles_out,
        (out_dir / COHORT_FILE).open("w", encoding="utf-8", newline="") as cohort_out,
    ):
        cohort = csv.writer(cohort_out, lineterminator="\n")
        cohort.writerow(COHORT_COLUMNS)
        for index in range(count):
            profile = generate_profile(params, seed, index)
            persona_counts[profile.persona] = persona_counts.get(profile.persona, 0) + 1
            line = json.dumps(profile_record(profile), separators=(",", ":"))
            profiles_out.write(line + "\n")
            for point in weekly_series(profile):
                cohort.writerow(
                    [
                        index,
                        profile.persona,
                        point.week_start.isoformat(),
                        point.discretionary_sen,
                        point.income_sen,
                    ]
                )
                cohort_rows += 1

    manifest = {
        "seed": seed,
        "profiles": count,
        "params_hash": params.hash(),
        "persona_counts": dict(sorted(persona_counts.items())),
        "files": {
            PROFILES_FILE: {"rows": count, "sha256": _sha256(out_dir / PROFILES_FILE)},
            COHORT_FILE: {"rows": cohort_rows, "sha256": _sha256(out_dir / COHORT_FILE)},
        },
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
    }
    (out_dir / MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write the synthetic student population.")
    parser.add_argument("--profiles", type=int, default=DEFAULT_PROFILES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    manifest = export_synthetic(load_params(), args.seed, args.profiles, args.out)
    print(f"wrote {manifest['profiles']} profiles to {args.out}")  # noqa: T201 - CLI entry point


if __name__ == "__main__":
    main()
