"""Simulation labels for Engine 2 (plan P5, task D3): `python -m ml.engine2_train.labels`.

For each synthetic profile this reproduces what the product would see on the profile's as-of day
and asks Engine 1 how likely the proposed plan is to leave the student short:

* the ledger up to the as-of day (nothing after it),
* recurring items = what recurring detection suggests from that ledger, all confirmed (the
  generator's recurring ground truth is an answer key and is never used),
* existing plans with the paid status they had on the as-of day,
* the provider limits the student has *recorded*,
* the served model, and the same random draws with and without the purchase,
* the as-of day drawn per profile across a full calendar year (`calendar.*` parameters), so the
  PTPTN position, the semester and the horizon differ from label to label, and a simulation that
  runs to the last instalment of the plan (ADR D-36).

The label is the simulated chance the cumulative margin goes below RM0 with the plan added (D-07,
D-33). Features come from `app.engines.risk.features` only (D-09).
"""

import argparse
import json
import zlib
from collections.abc import Callable, Iterator, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from app.engines.forecasting.bands import BAND_FILE, text_digest
from app.engines.forecasting.recurring import detect
from app.engines.forecasting.serving import served_forecaster
from app.engines.forecasting.simulate import RISK_CHECK_MAX_WEEKS, Forecaster
from app.engines.forecasting.summary import build_feature_inputs
from app.engines.risk.features import FEATURE_NAMES, FEATURE_SCHEMA_HASH, compute_features
from ml.datagen.params import Params, load_params
from ml.datagen.profile import StudentProfile, generate_dated_profile
from ml.engine2_train.provenance import git_commit, library_versions, sha256_file

DEFAULT_OUT = Path(__file__).resolve().parents[3] / "data" / "engine2"
DEFAULT_SEED = 20251228
DEFAULT_PROFILES = 11_000  # indices 10,000-10,999 are the engine v3 lockbox
LABELS_FILE = "labels.jsonl"
MANIFEST_FILE = "MANIFEST.json"
RUN_FILE = "labels.run.json"  # the settings a partial file was made with (for --resume)
LABEL_VERSION = "4"  # bump when the way a label is made changes
# 2: the simulation runs to the plan's last instalment (D-36) and each profile has its own as-of
#    day (D-31 note); the feature schema hash now covers the window constants (audit M2).
# 3: WP16 - the running margin starts from the profile's savings buffer (D-50) and the forecast
#    band is widened by history length (C2, `band_inflation.json`).
# 4: engine v3 - the served band rule floors each simulated MONTH at zero instead of each week
#    (D-60) and resamples a population error record below 26 weeks of history (D-61); the savings
#    feature is measured against expected outgoings (D-63); 11,000 profiles, the last 1,000 being
#    the new lockbox (plan 2026-10-18-engine-v3 §5.2).
PROGRESS_EVERY = 250
Transform = Callable[[list[dict[str, Any]], date], list[dict[str, Any]]]


def profile_seed(master_seed: int, index: int) -> int:
    """A stable seed per profile, so a label never depends on how many profiles are made."""
    return zlib.crc32(f"{master_seed}:{index}".encode())


def prepare(
    profile: StudentProfile,
    transform: Transform | None = None,
    item_transform: Transform | None = None,
) -> dict[str, Any]:
    """What the product would know on the profile's as-of day. Reads no answer key.

    `transform` changes the ledger before anything is detected from it; `item_transform` changes
    the confirmed recurring items after detection (the stress tests use both).
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
    if item_transform is not None:
        items = item_transform(items, as_of)
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
        "savings_buffer_sen": profile.savings_buffer_sen,  # what the student would record (D-50)
    }


def label_profile(
    profile: StudentProfile,
    forecaster: Forecaster,
    master_seed: int,
    paths: int = 1000,
    recentre_errors: bool = False,
) -> dict[str, Any] | None:
    """The label and features for one profile, or None if its ledger is locked.
    `recentre_errors` is the C6 sensitivity run only (the served bias term removed)."""
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
        savings_buffer_sen=known["savings_buffer_sen"],
        recentre_errors=recentre_errors,
    )
    if built is None:
        return None
    return {
        "index": profile.index,
        "label": built.p_with,
        "p_without": built.p_without,
        "features": compute_features(built.inputs),
        "bootstrap": built.with_plan.simulation.bootstrap,
        "horizon_capped": built.with_plan.simulation.horizon_capped
        or built.without.simulation.horizon_capped,
        "as_of": profile.as_of.isoformat(),
        # sensitivity only (ASSUMED 4): any single month short, instead of the running total
        "label_monthly": built.p_with_monthly,
        "p_without_monthly": built.p_without_monthly,
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
    recentre_errors: bool = False,
) -> Iterator[dict[str, Any]]:
    for index in range(first, count):
        profile = generate_dated_profile(params, master_seed, index)
        record = label_profile(profile, forecaster, master_seed, paths, recentre_errors)
        if record is None:
            yield {
                "index": index,
                "locked": True,
                "as_of": profile.as_of.isoformat(),
                "truth": _truth(profile),
            }
        else:
            yield {**record, "locked": False, "truth": _truth(profile)}


def served_model_files(forecaster: Forecaster) -> Any:
    """The artefact files (with hashes) of the served model, as its metadata names them."""
    return getattr(forecaster, "metadata", {}).get("files")


def _settings(
    params: Params,
    master_seed: int,
    paths: int,
    forecaster: Forecaster,
    count: int,
    recentre_errors: bool = False,
) -> dict:
    """Everything a label depends on besides the profile index: two runs agree only if these do.
    `profiles` (the count asked for) is recorded but not compared on resume: a run may be extended,
    never shortened."""
    return {
        "label_version": LABEL_VERSION,
        "seed": master_seed,
        "paths": paths,
        "params_hash": params.hash(),
        "feature_schema_hash": FEATURE_SCHEMA_HASH,
        "horizon_max_weeks": RISK_CHECK_MAX_WEEKS,
        "served_model": getattr(forecaster, "name", "unknown"),
        "served_model_files": served_model_files(forecaster),
        "band_rule_sha256": text_digest(BAND_FILE),
        "recentre_errors": recentre_errors,
        "git_commit": git_commit(),
        "profiles": count,
    }


def _comparable(settings: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in settings.items() if k != "profiles"}


def _resume_point(target: Path, sidecar: Path, settings: dict[str, Any]) -> int:
    """How many complete, in-order records `target` holds; a torn last line is cut off."""
    if not target.exists():
        return 0
    if not sidecar.exists() or _comparable(json.loads(sidecar.read_text(encoding="utf-8"))) != (
        _comparable(settings)
    ):
        raise ValueError(f"{target} was made with different settings; start a fresh run")
    kept = good_bytes = 0
    with target.open("rb") as handle:
        for line in handle:
            try:
                valid = line.endswith(b"\n") and json.loads(line)["index"] == kept
            except (ValueError, KeyError):
                valid = False
            if not valid:
                break
            kept += 1
            good_bytes += len(line)
    with target.open("r+b") as handle:
        handle.truncate(good_bytes)
    return kept


def _summarise(target: Path) -> dict[str, Any]:
    """Counts and the label distribution, read back from the file (so a resumed run agrees)."""
    labels: list[float] = []
    locked = capped = 0
    with target.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            locked += record["locked"]
            if not record["locked"]:
                labels.append(record["label"])
                capped += bool(record["horizon_capped"])
    quantiles = {str(q): float(np.quantile(labels, q / 100)) for q in (5, 25, 50, 75, 95)}
    return {"locked": locked, "capped": capped, "quantiles": quantiles if labels else {}}


def generate_labels(
    params: Params,
    master_seed: int,
    count: int,
    out_dir: Path,
    paths: int = 1000,
    forecaster: Forecaster | None = None,
    resume: bool = False,
    on_progress: Callable[[int], None] | None = None,
    recentre_errors: bool = False,
) -> dict[str, Any]:
    """Write `labels.jsonl` and `MANIFEST.json`. With `resume`, keep what an interrupted run of the
    same settings already wrote and continue after it (the result equals an uninterrupted run)."""
    forecaster = forecaster or served_forecaster()
    out_dir.mkdir(parents=True, exist_ok=True)
    target, sidecar = out_dir / LABELS_FILE, out_dir / RUN_FILE
    settings = _settings(params, master_seed, paths, forecaster, count, recentre_errors)
    first = _resume_point(target, sidecar, settings) if resume else 0
    if first > count:
        raise ValueError(
            f"{target} already holds {first} profiles; refusing to shorten it to {count}"
        )
    if not resume:
        target.write_bytes(b"")
    sidecar.write_text(json.dumps(settings, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        for record in iter_labels(
            params, master_seed, count, forecaster, paths, first, recentre_errors
        ):
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
            handle.flush()
            if on_progress and (record["index"] + 1) % PROGRESS_EVERY == 0:
                on_progress(record["index"] + 1)
    summary = _summarise(target)
    manifest = {
        **settings,
        "profiles": count,
        "locked_profiles": summary["locked"],
        "capped_profiles": summary["capped"],
        "feature_names": list(FEATURE_NAMES),
        "label_quantiles": summary["quantiles"],
        "as_of_window": {
            "start": str(params["calendar.as_of_window_start"]),
            "days": params["calendar.as_of_window_days"],
        },
        "file": {"name": LABELS_FILE, "sha256": sha256_file(target)},
        "git_commit": git_commit(),
        "versions": library_versions(),
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
    parser.add_argument("--resume", action="store_true", help="continue an interrupted run")
    parser.add_argument(
        "--recentre-errors",
        action="store_true",
        help="C6 sensitivity only: remove each record's mean error (never used for training)",
    )
    args = parser.parse_args(argv)
    manifest = generate_labels(
        load_params(),
        args.seed,
        args.profiles,
        args.out,
        args.paths,
        resume=args.resume,
        recentre_errors=args.recentre_errors,
        on_progress=lambda n: print(f"labelled {n}", flush=True),  # noqa: T201
    )
    print(f"labelled {manifest['profiles']} profiles ({manifest['locked_profiles']} locked)")  # noqa: T201


if __name__ == "__main__":
    main()
