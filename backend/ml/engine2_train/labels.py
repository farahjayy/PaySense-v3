"""Simulation labels for Engine 2 (plan P5, task D3): `python -m ml.engine2_train.labels`.

For each synthetic profile this reproduces what the product would see on the profile's as-of day
and asks Engine 1 how likely the proposed plan is to leave the student short:

* the ledger up to the as-of day (nothing after it),
* recurring items = what recurring detection suggests from that ledger, all confirmed (the
  generator's recurring ground truth is an answer key and is never used),
* existing plans with the paid status they had on the as-of day,
* the provider limits the student has *recorded*,
* the served model, and the same random draws with and without the purchase.

The label is the simulated chance the cumulative margin goes below RM0 with the plan added (D-07,
D-33). Features come from `app.engines.risk.features` only (D-09).
"""

import argparse
import hashlib
import json
import platform
import zlib
from collections.abc import Callable, Iterator, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from app.engines.forecasting.recurring import detect
from app.engines.forecasting.serving import served_forecaster
from app.engines.forecasting.simulate import Forecaster
from app.engines.forecasting.summary import build_feature_inputs
from app.engines.risk.features import FEATURE_NAMES, FEATURE_SCHEMA_HASH, compute_features
from ml.datagen.params import Params, load_params
from ml.datagen.profile import StudentProfile, generate_profile

DEFAULT_OUT = Path(__file__).resolve().parents[3] / "data" / "engine2"
DEFAULT_SEED = 20251228
DEFAULT_PROFILES = 10_000
LABELS_FILE = "labels.jsonl"
MANIFEST_FILE = "MANIFEST.json"
LABEL_VERSION = "1"  # bump when the way a label is made changes


def profile_seed(master_seed: int, index: int) -> int:
    """A stable seed per profile, so a label never depends on how many profiles are made."""
    return zlib.crc32(f"{master_seed}:{index}".encode())


def prepare(
    profile: StudentProfile,
    transform: Callable[[list[dict[str, Any]], date], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """What the product would know on the profile's as-of day. Reads no answer key.

    `transform` changes the ledger before anything is detected from it (the stress tests use it).
    """
    as_of = profile.as_of
    rows = [
        {**t.as_row(), "bnpl_plan_id": t.bnpl_plan_key}
        for t in profile.transactions
        if t.date <= as_of
    ]
    if transform is not None:
        rows = transform(rows, as_of)
    items = [
        {
            "kind": s.kind,
            "name": s.display_name,
            "match_text": s.name,
            "amount_sen": s.amount_sen,
            "cadence": s.cadence,
            "custom_interval_days": None,
            "anchor_date": s.anchor_date,
            "active": True,
        }
        for s in detect(rows, today=as_of)
    ]
    plans = [
        {
            "provider": plan.proposal.provider,
            "installments": [
                {
                    "seq": seq,
                    "due_date": i.due_date,
                    "amount_sen": i.amount_sen,
                    "is_paid": seq in plan.paid_dates and plan.paid_dates[seq] <= as_of,
                }
                for seq, i in enumerate(plan.proposal.instalments, start=1)
            ],
        }
        for plan in profile.bnpl.plans
    ]
    return {
        "rows": rows,
        "items": items,
        "plans": plans,
        "proposal": profile.purchase.proposal,
        "limits": dict(profile.bnpl.limits),
        "as_of": as_of,
    }


def label_profile(
    profile: StudentProfile, forecaster: Forecaster, master_seed: int, paths: int = 1000
) -> dict[str, Any] | None:
    """The label and features for one profile, or None if its ledger is locked."""
    known = prepare(profile)
    built = build_feature_inputs(
        rows=known["rows"],
        items=known["items"],
        plans=known["plans"],
        proposal=known["proposal"],
        provider_limits=known["limits"],
        today=known["as_of"],
        forecaster=forecaster,
        seed=profile_seed(master_seed, profile.index),
        paths=paths,
    )
    if built is None:
        return None
    return {
        "index": profile.index,
        "label": built.p_with,
        "p_without": built.p_without,
        "features": compute_features(built.inputs),
        "bootstrap": built.with_plan.simulation.bootstrap,
        "horizon_capped": built.with_plan.simulation.horizon_capped,
    }


def _truth(profile: StudentProfile) -> dict[str, Any]:
    """Facts kept for analysis only (never a feature, never read by training)."""
    return {
        "persona": profile.persona,
        "price_to_income": profile.purchase.price_sen / max(profile.expected_monthly_income_sen, 1),
    }


def iter_labels(
    params: Params,
    master_seed: int,
    count: int,
    forecaster: Forecaster,
    paths: int,
    first: int = 0,
) -> Iterator[dict[str, Any]]:
    for index in range(first, count):
        profile = generate_profile(params, master_seed, index)
        record = label_profile(profile, forecaster, master_seed, paths)
        if record is None:
            yield {"index": index, "locked": True, "truth": _truth(profile)}
        else:
            yield {**record, "locked": False, "truth": _truth(profile)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def generate_labels(
    params: Params,
    master_seed: int,
    count: int,
    out_dir: Path,
    paths: int = 1000,
    forecaster: Forecaster | None = None,
) -> dict[str, Any]:
    forecaster = forecaster or served_forecaster()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / LABELS_FILE
    locked = 0
    labels: list[float] = []
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for record in iter_labels(params, master_seed, count, forecaster, paths):
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
            locked += record["locked"]
            if not record["locked"]:
                labels.append(record["label"])
    manifest = {
        "label_version": LABEL_VERSION,
        "seed": master_seed,
        "profiles": count,
        "locked_profiles": locked,
        "paths": paths,
        "params_hash": params.hash(),
        "feature_schema_hash": FEATURE_SCHEMA_HASH,
        "feature_names": list(FEATURE_NAMES),
        "served_model": getattr(forecaster, "name", "unknown"),
        "served_model_files": getattr(forecaster, "metadata", {}).get("files"),
        "label_quantiles": {
            str(q): float(np.quantile(labels, q / 100)) for q in (5, 25, 50, 75, 95)
        }
        if labels
        else {},
        "file": {"name": LABELS_FILE, "sha256": _sha256(target)},
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
    }
    (out_dir / MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate Engine 2 simulation labels.")
    parser.add_argument("--profiles", type=int, default=DEFAULT_PROFILES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--paths", type=int, default=1000)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    manifest = generate_labels(load_params(), args.seed, args.profiles, args.out, args.paths)
    print(f"labelled {manifest['profiles']} profiles ({manifest['locked_profiles']} locked)")  # noqa: T201


if __name__ == "__main__":
    main()
