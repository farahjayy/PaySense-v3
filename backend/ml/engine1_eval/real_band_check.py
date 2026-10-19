"""Real-data check of the served band rule (plan 2026-10-19-local-completion, section 3).

Each rule is scored on the same origins of the same real series with the same random draws. A
rule's error record comes from `served_error_record`, the function serving and Engine 2's labels
use, so what is measured here is what is served: below the rule's population threshold the
population record, otherwise the user's own record, then the table's widening factor.

* R1: one widening factor of 1.5, the user's own record, every simulated week floored at zero;
* R2: the v2 table (D-54), the user's own record, weekly floor;
* R3: the rule in `models/engine1/` (monthly floor, population record below 26 weeks).

`decide` applies the plan's pre-registered rule: R3 is "clearly worse" on real data when it covers
the realised 13-week total more than 0.05 less often than R2, for histories of 26 weeks or more or
for 17-25 weeks, pooled over the real datasets and both kinds.
"""

import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np

from app.engines.forecasting.bands import BAND_FILE, BandRule, Bucket, load_band_rule
from app.engines.forecasting.service import (
    V1_ERROR_INFLATION,
    error_record,
    served_error_record,
)
from app.engines.forecasting.simulate import forecaster_for, path_bootstrap
from ml.engine1_eval.band_v3 import window_totals
from ml.engine1_eval.data import Series

HORIZON = 13
FIRST_ORIGIN = 17
STRIDE = 4
DRAWS = 300
BAND = (10, 90)
BUCKETS = ((17, 25, "17-25"), (26, 38, "26-38"), (39, 51, "39-51"), (52, None, "52+"))
SHORT_WEEKS = (17, 25)
LONG_WEEKS = (26, None)
LOSS_LIMIT = 0.05  # R3 is clearly worse when it covers more than this much less often than R2
RULE_V2 = BAND_FILE.parent / "rules" / "v2" / "band_inflation.json"
SCALE_WEEKS = 26  # bias is a share of the level over the latest 26 weeks, as in band_v3


@dataclass(frozen=True)
class Row:
    source: str
    series_id: str
    kind: str
    weeks: int  # weeks of history at the origin
    rule: str
    inside: bool  # the realised 13-week total fell inside the simulated P10-P90
    bias: float  # (simulated median - realised) / (recent level x 13)


@dataclass(frozen=True)
class Decision:
    long_gap: float  # coverage(R3) - coverage(R2), histories of 26 weeks or more
    short_gap: float  # the same for 17-25 weeks
    long_worse: bool
    short_worse: bool

    @property
    def clearly_worse(self) -> bool:
        return self.long_worse or self.short_worse


def bucket_label(weeks: int) -> str:
    for low, high, label in BUCKETS:
        if weeks >= low and (high is None or weeks <= high):
            return label
    raise ValueError(f"{weeks} weeks is below the shortest history ({FIRST_ORIGIN})")


def rules_under_test(rule_v2_path: Path = RULE_V2) -> dict[str, BandRule]:
    return {
        "R1": BandRule("v1", (Bucket(0, V1_ERROR_INFLATION, V1_ERROR_INFLATION),), "week"),
        "R2": load_band_rule(rule_v2_path),
        "R3": load_band_rule(),
    }


def score_series(
    series: Series,
    forecaster: Any,
    rules: Mapping[str, BandRule],
    seed: int,
    draws: int = DRAWS,
) -> list[Row]:
    """One row per origin and rule. Every rule at an origin gets a generator seeded the same way,
    so two rules with the same record and factor give the same score."""
    model = forecaster_for(forecaster, series.kind)
    tag = zlib.crc32(series.series_id.encode())
    rows: list[Row] = []
    for origin in range(FIRST_ORIGIN, len(series) - HORIZON + 1, STRIDE):
        history = np.asarray(series.values[:origin], dtype=float)
        monday = series.start + timedelta(days=7 * origin)
        actual = float(np.sum(series.values[origin : origin + HORIZON]))
        scale = max(float(np.mean(history[-SCALE_WEEKS:])) * HORIZON, 1.0)
        point = np.clip(model.forecast(history, HORIZON, series.start), 0, None)
        own = error_record(history, series.start, forecaster, series.kind)  # same for every rule
        for name, rule in rules.items():
            errors, _ = served_error_record(
                history, series.start, forecaster, series.kind, rule, own=own
            )
            if len(errors) == 0:
                continue
            rng = np.random.default_rng([seed, origin, tag])
            totals = window_totals(
                point + path_bootstrap(errors, HORIZON, draws, rng), monday, rule.clip
            )
            low, high = np.percentile(totals, BAND)
            rows.append(
                Row(
                    series.source,
                    series.series_id,
                    series.kind,
                    origin,
                    name,
                    bool(low <= actual <= high),
                    float((np.median(totals) - actual) / scale),
                )  # fmt: skip
            )
    return rows


def coverage(rows: Sequence[Row], rule: str, min_weeks: int, max_weeks: int | None) -> float | None:
    """Share of origins inside the band for `rule`, histories between the two limits (inclusive)."""
    part = [
        r.inside
        for r in rows
        if r.rule == rule and r.weeks >= min_weeks and (max_weeks is None or r.weeks <= max_weeks)
    ]
    return float(np.mean(part)) if part else None


def decide(rows: Sequence[Row]) -> Decision:
    """The plan's rule 3.3. A group with no rows for R2 or R3 raises instead of passing quietly."""
    gaps = []
    for limits in (LONG_WEEKS, SHORT_WEEKS):
        r3, r2 = (coverage(rows, rule, *limits) for rule in ("R3", "R2"))
        if r3 is None or r2 is None:
            label = f"{limits[0]}-{limits[1]}" if limits[1] else f"{limits[0]}+"
            raise ValueError(
                f"no {label} week origins for both R2 and R3; the rule cannot be applied"
            )
        gaps.append(r3 - r2)
    long_gap, short_gap = gaps
    # rounded so a loss of exactly the limit (0.75 - 0.80) is not tipped over by float noise
    return Decision(
        long_gap, short_gap, round(long_gap, 9) < -LOSS_LIMIT, round(short_gap, 9) < -LOSS_LIMIT
    )


def summary_rows(rows: Sequence[Row]) -> list[dict[str, Any]]:
    """Coverage and median bias per dataset, kind, history bucket and rule."""
    groups: dict[tuple[str, str, str, str], list[Row]] = {}
    for r in rows:
        groups.setdefault((r.source, r.kind, bucket_label(r.weeks), r.rule), []).append(r)
    order = {label: i for i, (_, _, label) in enumerate(BUCKETS)}
    out = []
    for (source, kind, bucket, rule), part in sorted(
        groups.items(), key=lambda kv: (kv[0][0], kv[0][1], order[kv[0][2]], kv[0][3])
    ):
        out.append(
            {
                "source": source, "kind": kind, "bucket": bucket, "rule": rule, "n": len(part),
                "coverage": float(np.mean([r.inside for r in part])),
                "bias": float(np.median([r.bias for r in part])),
            }
        )  # fmt: skip
    return out


def _pivot(rows: Sequence[Row]) -> list[dict[str, Any]]:
    cells: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = {}
    for item in summary_rows(rows):
        key = (item["source"], item["kind"], item["bucket"])
        cells.setdefault(key, {})[item["rule"]] = item
    return [
        {"source": s, "kind": k, "bucket": b, "rules": by_rule}
        for (s, k, b), by_rule in cells.items()
    ]


def _cell(by_rule: Mapping[str, Mapping[str, Any]], rule: str, field: str, fmt: str) -> str:
    item = by_rule.get(rule)
    return format(item[field], fmt) if item else "-"


def _table(rows: Sequence[Row]) -> list[str]:
    lines = [
        "| dataset | series | weeks of history | origins | inside P10-P90: R1 | R2 | R3 "
        "| median bias: R1 | R2 | R3 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cell in _pivot(rows):
        by_rule = cell["rules"]
        n = max(item["n"] for item in by_rule.values())
        inside = " | ".join(_cell(by_rule, r, "coverage", ".2f") for r in ("R1", "R2", "R3"))
        bias = " | ".join(_cell(by_rule, r, "bias", "+.3f") for r in ("R1", "R2", "R3"))
        lines.append(
            f"| {cell['source']} | {cell['kind']} | {cell['bucket']} | {n} | {inside} | {bias} |"
        )
    return lines


def render_section(rows: Sequence[Row]) -> str:
    """The report section: every cell, then the plan's rule applied to the real datasets only."""
    real = [r for r in rows if r.source != "synthetic"]
    lines = [
        "R1 is the single 1.5 factor, R2 the v2 table (D-54) and R3 the rule served now (monthly "
        "floor, population record below 26 weeks, refitted table). All three are scored on the "
        "same origins (from 17 weeks of history, every fourth week) with the same random draws; "
        "*inside P10-P90* should be 0.80 and *median bias* is (simulated median - realised) as "
        "a share of the recent level, above 0 meaning too high. The synthetic rows are the "
        "held-out Engine 1 test students scored by the same code, so the two can be read side "
        "by side.\n",
        *_table(rows),
        "",
        "### Rule from the plan, applied to the real datasets",
        "",
        "R3 is *clearly worse* if it covers the realised total more than 0.05 less often than R2, "
        "for histories of 26 weeks or more, or for 17-25 weeks, pooled over the real datasets "
        "and both series.\n",
    ]
    try:
        decision = decide(real)
    except ValueError as err:
        lines.append(f"The rule {err}.")
        return "\n".join(lines) + "\n"
    verdict = "yes" if decision.clearly_worse else "no"
    lines += [
        f"- coverage(R3) - coverage(R2), 26 weeks or more: {decision.long_gap:+.2f}",
        f"- coverage(R3) - coverage(R2), 17-25 weeks: {decision.short_gap:+.2f}",
        f"- R3 is clearly worse than R2 on real data: **{verdict}**",
    ]
    return "\n".join(lines) + "\n"
