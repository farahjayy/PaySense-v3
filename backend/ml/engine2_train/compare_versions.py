"""Engine 2, every version side by side, the bias-term sensitivity (WP16) and the engine v3
serve rule (plan 2026-10-18-engine-v3 §5.4):

    cd backend && uv run python -m ml.engine2_train.compare_versions

Reads only files other scripts made: the v1 labels (regenerated here with the v1 code; their
SHA-256 equals the committed v1 manifest), the v2 labels and the re-centred sensitivity labels
(`labels --recentre-errors`), both artefacts' metadata and both serving checks. Writes
`reports/engine2/versions.md`, `tables/versions.csv` and `tables/bias_sensitivity.csv`.
Nothing here trains, tunes or scores a model, and no number is typed in by hand.
"""

import argparse
import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from app.engines.forecasting.simulate import band
from app.engines.risk.features import BUFFER_FEATURE, EARLIER_BUFFER_FEATURES

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "engine2"
REPORTS = ROOT / "reports" / "engine2"
MODELS = ROOT / "backend" / "models" / "engine2"
BANDS = ("Safe", "Caution", "At Risk")
SATURATION = 0.02  # within this of exactly 0 or 1 (the P5 stop-rule margin)
SAFE_EDGE = 0.10
SERVING_DROP = 0.02  # plan §5.4 criterion 3: v3's serving band agreement may fall by at most this


def read_labels(path: Path) -> dict[int, dict[str, Any]]:
    """index -> {label, p_without, persona, buffer} for every profile that was not locked."""
    out: dict[int, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            r = json.loads(line)
            if r["locked"]:
                continue
            out[r["index"]] = {
                "label": float(r["label"]),
                "p_without": float(r["p_without"]),
                "persona": r.get("truth", {}).get("persona"),
                "buffer": _buffer(r["features"]),
            }
    return out


def _buffer(features: dict[str, float]) -> float:
    for name in (BUFFER_FEATURE, *EARLIER_BUFFER_FEATURES):
        if name in features:
            return float(features[name])
    return 0.0


def label_facts(labels: dict[int, dict[str, Any]]) -> dict[str, float]:
    y = np.array([r["label"] for r in labels.values()])
    base = np.array([r["p_without"] for r in labels.values()])
    bands_y = np.array([band(v) for v in y])
    moved = bands_y != np.array([band(v) for v in base])
    return {
        "profiles": float(len(y)),
        "median_label": float(np.median(y)),
        "mean_label": float(y.mean()),
        "share_label_exactly_0_or_1": float(((y == 0) | (y == 1)).mean()),
        "share_label_within_002_of_0_or_1": float(((y < SATURATION) | (y > 1 - SATURATION)).mean()),
        "share_short_before_purchase": float((base >= SAFE_EDGE).mean()),
        "share_band_decided_before_purchase": float((~moved).mean()),
        **{f"share_{b.lower().replace(' ', '_')}": float((bands_y == b).mean()) for b in BANDS},
    }


def model_facts(meta_path: Path) -> dict[str, Any]:
    if not meta_path.exists():
        return {}
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    m = meta.get("metrics", {})
    calibrated = (m.get("lockbox_calibrated") or {}).get("brier")
    constant = m.get("lockbox_constant_brier")
    benchmarks = m.get("lockbox_benchmarks") or {}
    return {
        "family": meta.get("family"),
        "target": meta.get("target", "p_with"),
        "lockbox_rule": m.get("lockbox_rule", "every tenth profile"),
        "features": len(meta.get("feature_names", [])),
        "cv_brier": m.get("cv_brier"),
        "lockbox_brier_calibrated": (m.get("lockbox_calibrated") or {}).get("brier"),
        "lockbox_brier_logistic": m.get("lockbox_logistic_brier"),
        "lockbox_brier_constant": constant,
        # the labels differ between versions, so raw Brier scores do not compare; this does
        "lockbox_brier_skill": (
            1 - calibrated / constant if calibrated is not None and constant else None
        ),
        "lockbox_band_agreement": m.get("lockbox_band_agreement"),
        "lockbox_auc_at_030": (m.get("lockbox_calibrated") or {}).get("auc_at_030"),
        "lockbox_brier_p_without": (benchmarks.get("p_without") or {}).get("brier"),
    }


def paired_change(old: dict[int, dict], new: dict[int, dict]) -> dict[str, Any]:
    """The same students in two label versions: what the engine changes did to their labels."""
    common = sorted(set(old) & set(new))
    a = np.array([old[i]["label"] for i in common])
    b = np.array([new[i]["label"] for i in common])
    base_a = np.array([old[i]["p_without"] for i in common])
    base_b = np.array([new[i]["p_without"] for i in common])
    bands_a, bands_b = [band(v) for v in a], [band(v) for v in b]
    return {
        "profiles": len(common),
        "mean_label_old": float(a.mean()),
        "mean_label_new": float(b.mean()),
        "mean_p_without_old": float(base_a.mean()),
        "mean_p_without_new": float(base_b.mean()),
        "mean_absolute_change": float(np.abs(b - a).mean()),
        "band_agreement": float(np.mean([x == y for x, y in zip(bands_a, bands_b, strict=True)])),
        "transitions": {
            f"{x} -> {y}": sum(1 for p, q in zip(bands_a, bands_b, strict=True) if (p, q) == (x, y))
            for x in BANDS
            for y in BANDS
        },
    }


def decide_engine2(v2: dict[str, Any], v3: dict[str, Any]) -> dict[str, Any]:
    """Plan §5.4: serve v3 only if all three criteria hold; a missing number fails its criterion."""

    def known(*values: Any) -> bool:
        return all(v is not None for v in values)

    s2, s3 = v2.get("lockbox_brier_skill"), v3.get("lockbox_brier_skill")
    b3, bp = v3.get("lockbox_brier_calibrated"), v3.get("lockbox_brier_p_without")
    a2, a3 = v2.get("serving_band_agreement"), v3.get("serving_band_agreement")
    criteria = [
        {
            "id": 1,
            "rule": "new-lockbox Brier skill (1 - B/B_const) at least v2's on its own lockbox",
            "holds": known(s2, s3) and s3 >= s2,
            "values": [s3, s2],
        },
        {
            "id": 2,
            "rule": "new-lockbox Brier below the predict-p_without benchmark's",
            "holds": known(b3, bp) and b3 < bp,
            "values": [b3, bp],
        },
        {
            "id": 3,
            "rule": f"serving-check band agreement at least v2's minus {SERVING_DROP:.2f}",
            "holds": known(a2, a3) and a3 >= a2 - SERVING_DROP - 1e-12,
            "values": [a3, a2],
        },
    ]
    return {"serve": all(c["holds"] for c in criteria), "criteria": criteria}


def serving_facts(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    s = json.loads(path.read_text(encoding="utf-8"))
    seconds = s.get("seconds") or {}
    return {
        "serving_band_agreement": s.get("band_agreement"),
        "serving_non_safe": s.get("non_safe"),
        "serving_non_safe_short_before_purchase": s.get("non_safe_short_before_purchase"),
        "serving_change_reaches_safe": s.get("suggestion_reaches_safe"),
        "serving_p95_seconds": seconds.get("p95") if isinstance(seconds, dict) else None,
    }


def bias_sensitivity(
    main: dict[int, dict[str, Any]], centred: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    common = sorted(set(main) & set(centred))
    a = np.array([main[i]["label"] for i in common])
    b = np.array([centred[i]["label"] for i in common])
    band_a = [band(v) for v in a]
    band_b = [band(v) for v in b]
    transitions = {
        (x, y): sum(1 for p, q in zip(band_a, band_b, strict=True) if (p, q) == (x, y))
        for x in BANDS
        for y in BANDS
    }
    personas = sorted({main[i]["persona"] for i in common if main[i]["persona"]})
    by_persona = {
        p: float(
            np.mean(
                [centred[i]["label"] - main[i]["label"] for i in common if main[i]["persona"] == p]
            )
        )  # fmt: skip
        for p in personas
    }
    return {
        "profiles": len(common),
        "mean_label_served": float(a.mean()),
        "mean_label_recentred": float(b.mean()),
        "mean_change": float((b - a).mean()),
        "mean_absolute_change": float(np.abs(b - a).mean()),
        "p95_absolute_change": float(np.percentile(np.abs(b - a), 95)),
        "band_agreement": float(np.mean([x == y for x, y in zip(band_a, band_b, strict=True)])),
        "transitions": transitions,
        "mean_change_by_persona": by_persona,
    }


def buffer_effect(v1: dict[int, dict], v2: dict[int, dict]) -> dict[str, Any]:
    """Paired by profile: the same student, ledger and purchase in both runs; v2 adds the buffer
    start (C5) and the new bands (C2), so a change mixes both, split by whether v2 gave a buffer."""
    common = sorted(set(v1) & set(v2))
    out = {}
    for name, keep in (("with a buffer", True), ("no buffer", False)):
        ids = [i for i in common if (v2[i]["buffer"] > 0) == keep]
        if not ids:
            continue
        old = np.array([v1[i]["label"] for i in ids])
        new = np.array([v2[i]["label"] for i in ids])
        out[name] = {
            "profiles": len(ids),
            "mean_label_v1": float(old.mean()),
            "mean_label_v2": float(new.mean()),
            "share_at_risk_v1": float(np.mean([band(v) == "At Risk" for v in old])),
            "share_at_risk_v2": float(np.mean([band(v) == "At Risk" for v in new])),
            "share_safe_v1": float(np.mean([band(v) == "Safe" for v in old])),
            "share_safe_v2": float(np.mean([band(v) == "Safe" for v in new])),
        }
    return out


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _v3_section(pairs: dict[str, Any] | None, verdict: dict[str, Any] | None) -> list[str]:
    if pairs is None or verdict is None:
        return []
    lines = [
        "## v3 against v2 for the same students (paired by profile)",
        "",
        "v3 (engine v3 round) makes its labels with Engine 1's band rule R3 (each simulated month "
        "floored at zero, a population error record below 26 weeks of history, a refitted "
        "table: D-60, D-61), measures the savings buffer against expected outgoings (D-63) and "
        "trains a two-part target (D-62). Indices 10,000-10,999 are new (its lockbox).",
        "",
        "| measure | value |",
        "|---|---|",
        *[f"| {k} | {_fmt(v)} |" for k, v in pairs.items() if k != "transitions"],
        "",
        "Band of the v2 label (rows) against the v3 label (columns):",
        "",
        "| v2 \\ v3 | " + " | ".join(BANDS) + " |",
        "|---|---|---|---|",
        *[
            f"| {x} | " + " | ".join(str(pairs["transitions"][f"{x} -> {y}"]) for y in BANDS) + " |"
            for x in BANDS
        ],
        "",
        "## Serve rule for v3 (written in the plan before any v3 label was made)",
        "",
    ]
    for c in verdict["criteria"]:
        values = " against ".join(_fmt(v) for v in c["values"])
        lines.append(f"{c['id']}. {c['rule']}: {values}: **{'holds' if c['holds'] else 'fails'}**.")
    lines += ["", f"**{'v3 is served' if verdict['serve'] else 'v2 stays served'}.**", ""]
    return lines


def render(
    facts: dict[str, dict[str, Any]],
    bias: dict[str, Any],
    buffer: dict[str, Any],
    pairs: dict[str, Any] | None = None,
    verdict: dict[str, Any] | None = None,
) -> str:
    versions = list(facts)
    keys = list(dict.fromkeys(k for f in facts.values() for k in f))
    rows = ["| " + " | ".join([k, *(_fmt(facts[v].get(k)) for v in versions)]) + " |" for k in keys]
    trans = bias["transitions"]
    trans_rows = [f"| {x} | " + " | ".join(str(trans[(x, y)]) for y in BANDS) + " |" for x in BANDS]
    buffer_rows = [
        f"| {name} | {v['profiles']} | {v['mean_label_v1']:.3f} | {v['mean_label_v2']:.3f} | "
        f"{v['share_safe_v1']:.3f} | {v['share_safe_v2']:.3f} | {v['share_at_risk_v1']:.3f} | "
        f"{v['share_at_risk_v2']:.3f} |"
        for name, v in buffer.items()
    ]
    persona_rows = [f"| {p} | {d:+.4f} |" for p, d in bias["mean_change_by_persona"].items()]
    return "\n".join(
        [
            "# Engine 2: every version side by side",
            "",
            "> Generated by `python -m ml.engine2_train.compare_versions` - do not edit by hand.",
            "> v1 = the P5/P6 model (labels version 2, 16 features, one band widening of 1.5). "
            "v2 = WP16 (labels version 3: the running margin starts from the savings buffer, "
            "D-50, and the band is widened by history length, C2; 17 features). v3 = the engine "
            "v3 round (labels version 4: Engine 1's band rule R3; the savings feature against "
            "outgoings; the two-part target; 11,000 profiles, lockbox indices 10,000-10,999). The "
            "v1 and v2 reports are kept unchanged in `v1/` and `v2/`.",
            "",
            "## Labels, model and serving check",
            "",
            "| measure | " + " | ".join(versions) + " |",
            "|---|" + "---|" * len(versions),
            *rows,
            "",
            "The v2 lockbox is the same students as v1's (every tenth profile index): it was "
            "scored once for v1 in P5 and once more here, with labels made by different code. "
            "The second scoring is disclosed rather than hidden; no choice in v2 was made on it. "
            "v3's lockbox is new (indices 10,000-10,999, never labelled before); v3 was also "
            "scored "
            "on the old lockbox for continuity only (`README.md`).",
            "",
            *_v3_section(pairs, verdict),
            "## What changed for the same students (paired by profile)",
            "",
            "Both changes act together (the buffer start and the new bands), so this is not the "
            "buffer's effect alone; students with no buffer show what the bands did by "
            "themselves.",
            "",
            "| students | count | mean label v1 | mean label v2 | Safe v1 | Safe v2 | At Risk v1 "
            "| At Risk v2 |",
            "|---|---|---|---|---|---|---|---|",
            *buffer_rows,
            "",
            "## Bias-term sensitivity (C6)",
            "",
            "Serving centres every simulated path on the user's own record of forecast errors, so "
            "a level the model has been getting wrong is carried into the future. A second label "
            "run (`labels --recentre-errors`) removed that mean error from every record. It is a "
            "sensitivity analysis only: nothing is trained on it and serving never re-centres.",
            "",
            "| measure | value |",
            "|---|---|",
            f"| students compared | {bias['profiles']} |",
            f"| mean label, served (bias kept) | {bias['mean_label_served']:.4f} |",
            f"| mean label, re-centred | {bias['mean_label_recentred']:.4f} |",
            f"| mean change (re-centred - served) | {bias['mean_change']:+.4f} |",
            f"| mean absolute change | {bias['mean_absolute_change']:.4f} |",
            f"| 95th percentile of the absolute change | {bias['p95_absolute_change']:.4f} |",
            f"| same band | {bias['band_agreement']:.1%} |",
            "",
            "Band of the served label (rows) against the re-centred label (columns):",
            "",
            "| served \\ re-centred | " + " | ".join(BANDS) + " |",
            "|---|---|---|---|",
            *trans_rows,
            "",
            "| persona (description only, never a feature) | mean change |",
            "|---|---|",
            *persona_rows,
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Engine 2 v1 and v2 side by side.")
    parser.add_argument("--v1-labels", type=Path, default=DATA / "v1" / "labels.jsonl")
    parser.add_argument("--v2-labels", type=Path, default=DATA / "v2" / "labels.jsonl")
    parser.add_argument("--v3-labels", type=Path, default=DATA / "labels.jsonl")
    parser.add_argument("--v3-model", type=Path, default=MODELS / "v3" / "metadata.json")
    parser.add_argument("--recentred", type=Path, default=DATA / "recentred" / "labels.jsonl")
    parser.add_argument("--out", type=Path, default=REPORTS)
    args = parser.parse_args(argv)
    v1, v2, v3 = (read_labels(p) for p in (args.v1_labels, args.v2_labels, args.v3_labels))
    centred = read_labels(args.recentred)
    facts = {
        "v1": {**label_facts(v1), **model_facts(MODELS / "v1" / "metadata.json"),
               **serving_facts(REPORTS / "v1" / "serving_check.json")},
        "v2": {**label_facts(v2), **model_facts(MODELS / "v2" / "metadata.json"),
               **serving_facts(REPORTS / "v2" / "serving_check.json")},
        "v3": {**label_facts(v3), **model_facts(args.v3_model),
               **serving_facts(REPORTS / "serving_check.json")},
    }  # fmt: skip
    pairs = paired_change(v2, v3)
    verdict = decide_engine2(facts["v2"], facts["v3"])
    (args.out / "tables").mkdir(parents=True, exist_ok=True)
    (args.out / "tables" / "engine2_v3_decision.json").write_text(
        json.dumps(verdict, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    bias = bias_sensitivity(v2, centred)
    buffer = buffer_effect(v1, v2)
    (args.out / "tables").mkdir(parents=True, exist_ok=True)
    with (args.out / "tables" / "versions.csv").open("w", encoding="utf-8", newline="") as h:
        writer = csv.writer(h)
        writer.writerow(["measure", *facts])
        for key in dict.fromkeys(k for f in facts.values() for k in f):
            writer.writerow([key, *(facts[v].get(key) for v in facts)])
    with (args.out / "tables" / "bias_sensitivity.csv").open(
        "w", encoding="utf-8", newline=""
    ) as h:
        writer = csv.writer(h)
        writer.writerow(["measure", "value"])
        for key, value in bias.items():
            if key not in ("transitions", "mean_change_by_persona"):
                writer.writerow([key, value])
        for (x, y), n in bias["transitions"].items():
            writer.writerow([f"transition {x} -> {y}", n])
        for persona, change in bias["mean_change_by_persona"].items():
            writer.writerow([f"mean change {persona}", change])
    (args.out / "versions.md").write_text(
        render(facts, bias, buffer, pairs, verdict), encoding="utf-8", newline="\n"
    )
    print(f"wrote {args.out / 'versions.md'}")  # noqa: T201
    print(json.dumps(verdict, indent=1))  # noqa: T201


if __name__ == "__main__":
    main()
