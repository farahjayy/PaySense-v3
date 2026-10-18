"""Engine 2, old and new side by side, and the bias-term sensitivity (WP16):

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
    return {
        "family": meta.get("family"),
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
    }


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


def render(facts: dict[str, dict[str, Any]], bias: dict[str, Any], buffer: dict[str, Any]) -> str:
    keys = list(dict.fromkeys(k for f in facts.values() for k in f))
    rows = [f"| {k} | {_fmt(facts['v1'].get(k))} | {_fmt(facts['v2'].get(k))} |" for k in keys]
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
            "# Engine 2: version 1 and version 2 side by side",
            "",
            "> Generated by `python -m ml.engine2_train.compare_versions` - do not edit by hand.",
            "> v1 = the P5/P6 model (labels version 2, 16 features, one band widening of 1.5). "
            "v2 = WP16 (labels version 3: the running margin starts from the savings buffer, "
            "D-50, and the band is widened by history length, C2; 17 features). The v1 report "
            "is kept unchanged in `v1/`.",
            "",
            "## Labels, model and serving check",
            "",
            "| measure | v1 | v2 |",
            "|---|---|---|",
            *rows,
            "",
            "The v2 lockbox is the same students as v1's (every tenth profile index): it was "
            "scored once for v1 in P5 and once more here, with labels made by different code. "
            "The second scoring is disclosed rather than hidden; no choice in v2 was made on it.",
            "",
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
    parser.add_argument("--v2-labels", type=Path, default=DATA / "labels.jsonl")
    parser.add_argument("--recentred", type=Path, default=DATA / "recentred" / "labels.jsonl")
    parser.add_argument("--out", type=Path, default=REPORTS)
    args = parser.parse_args(argv)
    v1, v2 = read_labels(args.v1_labels), read_labels(args.v2_labels)
    centred = read_labels(args.recentred)
    facts = {
        "v1": {**label_facts(v1), **model_facts(MODELS / "v1" / "metadata.json"),
               **serving_facts(REPORTS / "v1" / "serving_check.json")},
        "v2": {**label_facts(v2), **model_facts(MODELS / "v2" / "metadata.json"),
               **serving_facts(REPORTS / "serving_check.json")},
    }  # fmt: skip
    bias = bias_sensitivity(v2, centred)
    buffer = buffer_effect(v1, v2)
    (args.out / "tables").mkdir(parents=True, exist_ok=True)
    with (args.out / "tables" / "versions.csv").open("w", encoding="utf-8", newline="") as h:
        writer = csv.writer(h)
        writer.writerow(["measure", "v1", "v2"])
        for key in dict.fromkeys(k for f in facts.values() for k in f):
            writer.writerow([key, facts["v1"].get(key), facts["v2"].get(key)])
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
        render(facts, bias, buffer), encoding="utf-8", newline="\n"
    )
    print(f"wrote {args.out / 'versions.md'}")  # noqa: T201


if __name__ == "__main__":
    main()
