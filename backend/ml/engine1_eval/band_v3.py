"""Engine v3 band candidate R3 (F1 + F2 + refit), checked on a fresh group and decided by a rule
written before it ran (`refdocs/plans/2026-10-18-engine-v3.md` §4):

    cd backend && uv run python -m ml.engine1_eval.band_v3 fit
    cd backend && uv run python -m ml.engine1_eval.outcome_check      # writes the Brier gate (4)
    cd backend && uv run python -m ml.engine1_eval.band_v3 decide [--apply]

Rules compared (all on the served LSTM unless named):
* R1: one widening factor of 1.5, the user's own record, every simulated week floored at zero;
* R2: the served table of D-54 (`models/engine1/rules/v2/band_inflation.json`), weekly floor;
* R3: monthly floor (D-60), a population record of 13-week ratio error paths below 26 weeks of
  history (D-61), and a table refitted under both; written to `models/engine1/rules/v3/`;
* MA13-R3: the 13-week moving average run through the same R3 method (its own population record
  and table), as the benchmark.

Groups (plan §4.2): the population record is fitted on P, the R3 table on D (the 300 students
the R2 table was fitted on), and everything is scored once on the fresh group F. `fit` writes the
candidate files, `reports/engine1/tables/band_v3.json` and `reports/engine1/band_v3.md`;
`decide` adds the outcome check's Brier interval, applies criteria 1-4 and, with `--apply`,
copies R3 into `models/engine1/` only when every criterion holds.
"""

import argparse
import json
import shutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from app.engines.forecasting.bands import BAND_FILE, BandRule, load_band_rule, parse_rule
from app.engines.forecasting.flows import month_key
from app.engines.forecasting.models import MovingAverage
from app.engines.forecasting.onnx_model import load_served
from app.engines.forecasting.population import (
    HORIZON_WEEKS,
    digest,
    recent_level,
    write_population,
)
from app.engines.forecasting.service import V1_ERROR_INFLATION, error_record
from app.engines.forecasting.simulate import _month_weights, forecaster_for, path_bootstrap
from ml.engine1_eval.band_calibration import (
    BUCKETS,
    COHORT,
    DEV_PROFILES,
    EVAL_POOL,
    GRID,
    SEED,
    TARGET,
    bucket_of,
    dev_profiles,
)
from ml.engine1_eval.band_calibration import test_profiles as heldout_profiles
from ml.engine1_eval.band_fresh_check import fresh_profiles
from ml.engine1_eval.data import Series
from ml.engine1_eval.loaders.synthetic import DEFAULT_PATH, load_synthetic

ROOT = Path(__file__).resolve().parents[3]
MODELS = ROOT / "backend" / "models" / "engine1"
RULE_V2 = MODELS / "rules" / "v2" / "band_inflation.json"
RULE_V3_DIR = MODELS / "rules" / "v3"
MA13_RULE_DIR = ROOT / "reports" / "engine1" / "tables" / "ma13_rule_v3"
RESULTS = ROOT / "reports" / "engine1" / "tables" / "band_v3.json"
OUTCOME_GATE = ROOT / "reports" / "engine1" / "tables" / "outcome_check_v3.json"
REPORT = ROOT / "reports" / "engine1" / "band_v3.md"

P_PROFILES = 300
F_PROFILES = 500
POP_LENGTHS = (17, 19, 21, 23, 25)
BELOW_WEEKS = 26  # a population record below this many weeks of history; the user's own from it
HORIZON = HORIZON_WEEKS
STRIDE = 4
DRAWS = 300
FIRST_ORIGIN = 17
BOOTSTRAP_DRAWS = 2000
KINDS = ("spend", "income")
GRID_RULES = ("R3", "MA13-R3")
NAMES = {
    "R1": f"x{V1_ERROR_INFLATION} (R1)",
    "R2": "served table (R2)",
    "R3": "candidate (R3)",
    "MA13-R3": "MA13, R3 (benchmark)",
}
CELL_LOSS = 0.05


# --- groups --------------------------------------------------------------------------------------


def _used(seed: int) -> set[int]:
    from ml.engine1_eval.outcome_check import outcome_profiles  # outcome_check imports this module

    return (
        set(dev_profiles(DEV_PROFILES, seed))
        | set(fresh_profiles(seed=seed))
        | set(outcome_profiles(seed=seed))
        | set(heldout_profiles(seed))
    )


def _pool(exclude: set[int]) -> list[int]:
    return [i for i in range(EVAL_POOL, COHORT) if i % 10 != 0 and i not in exclude]


def population_profiles(count: int = P_PROFILES, seed: int = SEED) -> list[int]:
    rng = np.random.default_rng(seed + 6)
    return sorted(int(i) for i in rng.choice(_pool(_used(seed)), size=count, replace=False))


def fresh_v3_profiles(count: int = F_PROFILES, seed: int = SEED) -> list[int]:
    exclude = _used(seed) | set(population_profiles(seed=seed))
    rng = np.random.default_rng(seed + 7)
    return sorted(int(i) for i in rng.choice(_pool(exclude), size=count, replace=False))


def population_windows(profile: int, length: int, seed: int = SEED) -> list[tuple[int, int]]:
    """(window end, history length): one seeded end per length, so the 13 weeks after it exist."""
    rng = np.random.default_rng([seed, profile, 6])
    return [(int(rng.integers(n, length - HORIZON + 1)), n) for n in POP_LENGTHS]


# --- the population record -----------------------------------------------------------------------


def _profile(series: Series) -> int:
    return int(series.series_id.split("-")[1])


def population_paths(series: Iterable[Series], forecaster) -> dict[str, np.ndarray]:
    """13-week error paths as a share of each window's recent level, pooled by kind."""
    rows: dict[str, list[np.ndarray]] = {kind: [] for kind in KINDS}
    for s in series:
        model = forecaster_for(forecaster, s.kind)
        for end, length in population_windows(_profile(s), len(s)):
            history = np.asarray(s.values[end - length : end], dtype=float)
            level = recent_level(history)
            if level <= 0:
                continue
            start = s.start + timedelta(days=7 * (end - length))
            forecast = np.clip(model.forecast(history, HORIZON, start), 0, None)
            rows[s.kind].append((s.values[end : end + HORIZON] - forecast) / level)
    return {k: np.array(v, dtype=float).reshape(len(v), HORIZON) for k, v in rows.items()}


# --- totals --------------------------------------------------------------------------------------


@lru_cache(maxsize=4096)
def _weights(first_monday: date, weeks: int) -> np.ndarray:
    last = first_monday + timedelta(days=7 * weeks - 1)
    months = sorted({month_key(first_monday + timedelta(days=d)) for d in range(7 * weeks)})
    weights = _month_weights(first_monday, weeks, first_monday, last, months)
    weights.setflags(write=False)
    return weights


def window_totals(sims: np.ndarray, first_monday: date, clip: str) -> np.ndarray:
    """Total of each simulated path over its weeks, floored per week or per calendar month
    (the same day weights as `simulate`)."""
    sims = np.asarray(sims, dtype=float)
    if clip == "week":
        return np.clip(sims, 0, None).sum(axis=1)
    return np.clip(sims @ _weights(first_monday, sims.shape[1]), 0, None).sum(axis=1)


# --- records -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Record:
    profile: int
    kind: str
    weeks: int
    inside: dict[str, Any]  # R1/R2: bool; R3/MA13-R3: bool per GRID factor
    bias: dict[str, Any]  # (simulated median - actual) / (recent level x 13); same shapes


def _score(totals: np.ndarray, actual: float, scale: float) -> tuple[bool, float]:
    low, high = np.percentile(totals, (10, 90))
    return bool(low <= actual <= high), float((np.median(totals) - actual) / scale)


def _grid(point, record, sampled, monday, actual, scale) -> tuple[np.ndarray, np.ndarray]:
    centre = record.mean() if record.size else 0.0
    inside = np.zeros(len(GRID), dtype=bool)
    bias = np.zeros(len(GRID))
    for i, factor in enumerate(GRID):
        sims = point + centre + factor * (sampled - centre)
        inside[i], bias[i] = _score(window_totals(sims, monday, "month"), actual, scale)
    return inside, bias


def records_for(
    series: Series,
    models: Mapping[str, Any],
    rule_v2: BandRule,
    pops: Mapping[str, Mapping[str, np.ndarray]],
    rng: np.random.Generator,
) -> list[Record]:
    """Every origin of one series under R1, R2, R3 (LSTM) and R3 (MA13)."""
    out = []
    for origin in range(FIRST_ORIGIN, len(series) - HORIZON + 1, STRIDE):
        history = np.asarray(series.values[:origin], dtype=float)
        monday = series.start + timedelta(days=7 * origin)
        actual = float(np.sum(series.values[origin : origin + HORIZON]))
        scale = max(float(np.mean(history[-26:])) * HORIZON, 1.0)
        inside: dict[str, Any] = {}
        bias: dict[str, Any] = {}
        for key, rule_name in (("lstm", "R3"), ("ma13", "MA13-R3")):
            forecaster = models[key]
            model = forecaster_for(forecaster, series.kind)
            point = np.clip(model.forecast(history, HORIZON, series.start), 0, None)
            own, _ = error_record(history, series.start, forecaster, series.kind)
            sampled_own = path_bootstrap(own, HORIZON, DRAWS, rng)
            if key == "lstm":
                centre = own.mean() if own.size else 0.0
                for name, factor in (
                    ("R1", V1_ERROR_INFLATION),
                    ("R2", rule_v2.factor(origin, series.kind)),
                ):
                    sims = point + centre + factor * (sampled_own - centre)
                    totals = window_totals(sims, monday, "week")
                    inside[name], bias[name] = _score(totals, actual, scale)
            if origin < BELOW_WEEKS:
                record = pops[key][series.kind] * recent_level(history)
                sampled = path_bootstrap(record, HORIZON, DRAWS, rng)
            else:
                record, sampled = own, sampled_own
            inside[rule_name], bias[rule_name] = _grid(
                point, record, sampled, monday, actual, scale
            )
        out.append(Record(_profile(series), series.kind, origin, inside, bias))
    return out


# --- fitting and scores --------------------------------------------------------------------------


def fit_table(records: Sequence[Record], method: str) -> dict[str, list[float]]:
    """Per kind and bucket: the smallest factor whose coverage reaches TARGET, else the best."""
    table: dict[str, list[float]] = {}
    for kind in KINDS:
        factors = []
        for b in range(len(BUCKETS)):
            part = [r for r in records if r.kind == kind and bucket_of(r.weeks) == b]
            if not part:
                factors.append(GRID[0])
                continue
            rates = np.mean([r.inside[method] for r in part], axis=0)
            reaching = [i for i, rate in enumerate(rates) if rate >= TARGET]
            factors.append(GRID[reaching[0] if reaching else int(np.argmax(rates))])
        table[kind] = factors
    return table


def _value(record: Record, attr: str, method: str, table: Mapping[str, list[float]] | None):
    value = getattr(record, attr)[method]
    if method in GRID_RULES:
        if table is None:
            raise ValueError(f"{method} needs its fitted table")
        return value[GRID.index(table[record.kind][bucket_of(record.weeks)])]
    return value


def coverage(records: Sequence[Record], method: str, table=None) -> float | None:
    if not records:
        return None
    return float(np.mean([_value(r, "inside", method, table) for r in records]))


def median_bias(records: Sequence[Record], method: str, table=None) -> float | None:
    if not records:
        return None
    return float(np.median([_value(r, "bias", method, table) for r in records]))


def student_bootstrap(
    records: Sequence[Record], table: Mapping[str, list[float]], kind: str, draws: int, seed: int
) -> dict[str, list[float]]:
    """95% intervals over students for R3 - R2: coverage, and |median bias|."""
    part = [r for r in records if r.kind == kind]
    profiles = np.array([r.profile for r in part])
    ids = np.unique(profiles)
    members = [np.flatnonzero(profiles == p) for p in ids]
    in2 = np.array([r.inside["R2"] for r in part], dtype=float)
    in3 = np.array([_value(r, "inside", "R3", table) for r in part], dtype=float)
    b2 = np.array([r.bias["R2"] for r in part])
    b3 = np.array([_value(r, "bias", "R3", table) for r in part])

    def stats(index: np.ndarray) -> tuple[float, float]:
        cover = in3[index].mean() - in2[index].mean()
        shrink = abs(np.median(b3[index])) - abs(np.median(b2[index]))
        return float(cover), float(shrink)

    rng = np.random.default_rng(seed)
    sampled = [
        stats(np.concatenate([members[i] for i in rng.integers(0, len(ids), len(ids))]))
        for _ in range(draws)
    ]
    point = stats(np.arange(len(part)))
    out = {}
    for j, name in enumerate(("coverage_r3_minus_r2", "abs_bias_r3_minus_r2")):
        low, high = np.percentile([s[j] for s in sampled], (2.5, 97.5))
        out[name] = [point[j], float(low), float(high)]
    return out


# --- the decision (plan §4.4) ---


def decide(fresh: Mapping[str, Any], outcome: Mapping[str, Sequence[float]] | None) -> dict:
    """Criteria 1-4, each with the numbers it was judged on; serve only if all hold."""
    overall, cells = fresh["overall"], fresh["cells"]
    one = all(
        abs(overall[k]["R3"]["coverage"] - TARGET) < abs(overall[k]["R2"]["coverage"] - TARGET)
        for k in KINDS
    )
    two = all(abs(overall[k]["R3"]["bias"]) < abs(overall[k]["R2"]["bias"]) for k in KINDS)
    lost = [
        (k, b, c2, c3)
        for k in KINDS
        for b, (c2, c3) in enumerate(cells[k])
        if c3 < min(c2 - CELL_LOSS, TARGET) - 1e-9
    ]
    four = outcome is not None and all(float(v[1]) <= 0 for v in outcome.values())
    criteria = [
        {"id": 1, "holds": one, "rule": "overall coverage moves toward 0.80 for both kinds"},
        {"id": 2, "holds": two, "rule": "|median bias| shrinks for both kinds"},
        {
            "id": 3,
            "holds": not lost,
            "rule": "no kind x bucket cell below min(R2 - 0.05, 0.80)",
            "cells_lost": [list(x) for x in lost],
        },
        {
            "id": 4,
            "holds": four,
            "rule": "outcome-check Brier R3 - R2: 95% interval not entirely above 0, both cuts",
            "outcome": {k: list(v) for k, v in (outcome or {}).items()},
        },
    ]
    return {"serve": all(c["holds"] for c in criteria), "criteria": criteria}


# --- summary and page ---


def _bucket_label(b: int) -> str:
    return f"{BUCKETS[b]}-{BUCKETS[b + 1] - 1}" if b + 1 < len(BUCKETS) else f"{BUCKETS[b]}+"


def _rows(records: Sequence[Record], tables: Mapping[str, Any]) -> list[dict]:
    rows = []
    for kind in KINDS:
        groups = [(b, _bucket_label(b)) for b in range(len(BUCKETS))] + [(None, "all")]
        for b, label in groups:
            part = [r for r in records if r.kind == kind and (b is None or bucket_of(r.weeks) == b)]
            row: dict[str, Any] = {"kind": kind, "weeks": label, "origins": len(part)}
            for method in NAMES:
                table = tables.get(method)
                row[f"coverage_{method}"] = coverage(part, method, table)
                row[f"bias_{method}"] = median_bias(part, method, table)
                if method in GRID_RULES and b is not None:
                    row[f"factor_{method}"] = table[kind][b]
            rows.append(row)
    return rows


def summarise(
    dev: Sequence[Record],
    fresh: Sequence[Record],
    tables: Mapping[str, Mapping[str, list[float]]],
    rule_v2: BandRule,
    population: Mapping[str, np.ndarray],
    ids: Mapping[str, Sequence[int]],
    bootstrap_draws: int = BOOTSTRAP_DRAWS,
) -> dict[str, Any]:
    fresh_rows = _rows(fresh, tables)

    def overall(kind: str, method: str) -> dict[str, float]:
        row = next(r for r in fresh_rows if r["kind"] == kind and r["weeks"] == "all")
        return {"coverage": row[f"coverage_{method}"], "bias": row[f"bias_{method}"]}

    cells = {
        kind: [
            (r["coverage_R2"], r["coverage_R3"])
            for r in fresh_rows
            if r["kind"] == kind and r["weeks"] != "all" and r["origins"]
        ]
        for kind in KINDS
    }
    return {
        "groups": {name: len(v) for name, v in ids.items()},
        "group_ids": {name: list(map(int, v)) for name, v in ids.items()},
        "population_paths": {k: int(len(v)) for k, v in population.items()},
        "population_mean_ratio_error": {
            k: (float(np.mean(v)) if len(v) else None) for k, v in population.items()
        },
        "tables": {m: {k: list(v) for k, v in t.items()} for m, t in tables.items()},
        "rule_v2": {k: [rule_v2.factor(low, k) for low in BUCKETS] for k in KINDS},
        "development": _rows(dev, tables),
        "fresh": fresh_rows,
        "decision_inputs": {
            "overall": {k: {m: overall(k, m) for m in ("R2", "R3")} for k in KINDS},
            "cells": cells,
        },
        "bootstrap": {
            k: student_bootstrap(fresh, tables["R3"], k, bootstrap_draws, SEED + 8) for k in KINDS
        },
    }


def _f(value: float | None, digits: int = 2, sign: bool = False) -> str:
    if value is None:
        return "-"
    return f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"


def _table(rows: Sequence[dict]) -> list[str]:
    out = [
        "| series | weeks of history | origins | "
        + " | ".join(f"inside, {NAMES[m]}" for m in NAMES)
        + " | "
        + " | ".join(f"median bias, {NAMES[m]}" for m in NAMES)
        + " | factor R3 | factor MA13-R3 |",
        "|---|---|---|" + "---|" * (2 * len(NAMES)) + "---|---|",
    ]
    for r in rows:
        out.append(
            f"| {r['kind']} | {r['weeks']} | {r['origins']} | "
            + " | ".join(_f(r[f"coverage_{m}"]) for m in NAMES)
            + " | "
            + " | ".join(_f(r[f"bias_{m}"], 3, sign=True) for m in NAMES)
            + f" | {r.get('factor_R3', '')} | {r.get('factor_MA13-R3', '')} |"
        )
    return out


def render(
    summary: Mapping[str, Any],
    verdict: Mapping[str, Any] | None,
    outcome: Mapping[str, Sequence[float]] | None = None,
) -> str:
    groups = summary["groups"]
    t3 = summary["tables"]["R3"]
    lines = [
        "# Engine 1 band candidate R3: monthly clip, population record, refit (engine v3)",
        "",
        "> Generated by `python -m ml.engine1_eval.band_v3` - do not edit by hand. Plan: "
        "`refdocs/plans/2026-10-18-engine-v3.md` (groups, metrics and the serve rule were "
        "written there before this ran).",
        "",
        "Each row is a point in a synthetic student's history (origins from week 17 every 4 "
        f"weeks), {DRAWS} resampled {HORIZON}-week totals per rule, and the share of points whose "
        "realised total fell inside the simulated P10-P90 (*inside*, should be 0.80). *Median "
        "bias* is the median of (simulated median - realised) / (recent level x 13): above 0 = "
        "too high.",
        "",
        f"- **{NAMES['R1']}**: the user's own error record widened by {V1_ERROR_INFLATION}, every "
        "simulated week floored at zero (engine v1).",
        f"- **{NAMES['R2']}**: the D-54 table, weekly floor (served before this round).",
        f"- **{NAMES['R3']}**: each calendar month's total floored at zero instead of each week "
        f"(D-60); below {BELOW_WEEKS} weeks of history a population record of 13-week ratio "
        "error paths times the user's recent level (D-61); the table refitted on the development "
        "students under both.",
        f"- **{NAMES['MA13-R3']}**: the 13-week moving average through the same R3 method, with "
        "its own population record and table.",
        "",
        "## Students",
        "",
        "| group | students | use |",
        "|---|---|---|",
        f"| D | {groups['D']} | the R2 table's fitting students; the R3 table is fitted here |",
        f"| P | {groups['P']} | new; the population record is fitted here (one seeded window per "
        f"history length {', '.join(map(str, POP_LENGTHS))} weeks per student) |",
        f"| F | {groups['F']} | new and fresh: scored once, nothing fitted or chosen on it |",
        "",
        "All are cohort indices 4,000-9,999 not divisible by 10 (never Engine 2's lockbox); P and "
        "F exclude the earlier fresh-check students, the outcome-check students and the 60 "
        "Engine 1 test students.",
        "",
        f"Population record: {summary['population_paths']['spend']} spending paths and "
        f"{summary['population_paths']['income']} income paths (windows whose recent level was 0 "
        "are left out); mean ratio error (actual - forecast, share of the level) spending "
        f"{_f(summary['population_mean_ratio_error']['spend'], 3, True)}, income "
        f"{_f(summary['population_mean_ratio_error']['income'], 3, True)}.",
        "",
        "## Fresh check (group F)",
        "",
        *_table(summary["fresh"]),
        "",
        "Student-level paired bootstrap (95% interval, "
        f"{BOOTSTRAP_DRAWS} draws over F's students), R3 minus R2:",
        "",
    ]
    for kind in KINDS:
        boot = summary["bootstrap"].get(kind)
        if boot:
            c, b = boot["coverage_r3_minus_r2"], boot["abs_bias_r3_minus_r2"]
            lines.append(
                f"- {kind}: coverage {c[0]:+.3f} ({c[1]:+.3f} to {c[2]:+.3f}); |median bias| "
                f"{b[0]:+.3f} ({b[1]:+.3f} to {b[2]:+.3f}; below 0 = R3 is less biased)."
            )
    lines += [
        "",
        "## Development fit (group D)",
        "",
        *_table(summary["development"]),
        "",
        "## The R3 table (`backend/models/engine1/rules/v3/band_inflation.json`)",
        "",
        "| weeks of history from | spend R2 | spend R3 | income R2 | income R3 |",
        "|---|---|---|---|---|",
        *[
            f"| {low} | {summary['rule_v2']['spend'][b]} | {t3['spend'][b]} | "
            f"{summary['rule_v2']['income'][b]} | {t3['income'][b]} |"
            for b, low in enumerate(BUCKETS)
        ],
        "",
        "## Decision (plan §4.4)",
        "",
    ]
    if verdict is None:
        lines.append("Pending: run the outcome check, then `band_v3 decide`.")
    else:
        for c in verdict["criteria"]:
            lines.append(f"{c['id']}. {c['rule']}: **{'holds' if c['holds'] else 'fails'}**.")
            if c.get("cells_lost"):
                lines.append(f"   Cells lost: {c['cells_lost']}.")
        for cut, (delta, low, high) in (outcome or {}).items():
            lines.append(
                f"   Outcome check, cut {cut} weeks: Brier R3 - R2 {delta:+.4f} "
                f"(95% interval {low:+.4f} to {high:+.4f})."
            )
        result = "R3 is served" if verdict["serve"] else "R2 stays served"
        lines += ["", f"**{result}.**"]
    lines += [
        "",
        "## Limits",
        "",
        "- Synthetic students only; MoneyData and Berka cannot be downloaded in this environment, "
        "so the real-data check of R3 is a local step.",
        "- The cohort holds ALL income; serving forecasts only income not covered by a confirmed "
        "recurring item (note N2). Income coverage here measures a series serving mostly places "
        "as known flows.",
        "- Short histories in D and F start at the cohort's first week, so the 17-25 bucket is "
        "scored in one season; the population record's windows are spread across the year.",
        "",
    ]
    return "\n".join(lines)


# --- files ---------------------------------------------------------------------------------------


def _rule_json(table: Mapping[str, list[float]], pop_file: Path, provenance: dict) -> dict:
    rule = {
        "version": "3",
        "replaces": "band rule v2 (D-54): weekly clip, the user's own record at every length",
        "target_coverage": TARGET,
        "clip": "month",
        "population_record": {
            "file": pop_file.name,
            "sha256": digest(pop_file),
            "below_weeks": BELOW_WEEKS,
        },
        "buckets": [
            {"min_weeks": low, "spend": table["spend"][b], "income": table["income"][b]}
            for b, low in enumerate(BUCKETS)
        ],
        "fitted_on": provenance,
        "generated_by": "python -m ml.engine1_eval.band_v3 fit",
    }
    parse_rule(rule)
    return rule


def write_rule(folder: Path, table, paths, provenance_pop: dict, provenance_table: dict) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    pop_file = folder / "population_errors.json"
    write_population(pop_file, paths, provenance_pop)
    rule_file = folder / "band_inflation.json"
    rule = _rule_json(table, pop_file, provenance_table)
    rule_file.write_text(json.dumps(rule, indent=2) + "\n", encoding="utf-8", newline="\n")
    load_band_rule.cache_clear()
    return rule_file


def _load(path: Path, ids: set[int]) -> list[Series]:
    return list(load_synthetic(path, profile_ids=ids))


def fit(synthetic: Path) -> dict[str, Any]:
    served = load_served()
    models = {"lstm": served, "ma13": MovingAverage(13)}
    rule_v2 = load_band_rule(RULE_V2)
    ids = {"D": dev_profiles(), "P": population_profiles(), "F": fresh_v3_profiles()}
    series = _load(synthetic, set().union(*map(set, ids.values())))
    by_group = {g: [s for s in series if _profile(s) in set(v)] for g, v in ids.items()}
    pops = {key: population_paths(by_group["P"], model) for key, model in models.items()}
    rng = np.random.default_rng(SEED + 9)
    dev = [r for s in by_group["D"] for r in records_for(s, models, rule_v2, pops, rng)]
    tables = {m: fit_table(dev, m) for m in GRID_RULES}
    provenance_pop = {
        "students": len(ids["P"]),
        "rule": "group P of the engine v3 plan: new cohort students 4000-9999, not divisible by "
        "10, none of the band-fit, fresh-check, outcome-check or Engine 1 test students",
        "history_weeks": list(POP_LENGTHS),
        "seed": SEED,
    }
    provenance_table = {
        "students": len(ids["D"]),
        "rule": "group D: the 300 students the v2 table was fitted on",
        "origins_per_kind": len(dev) // len(KINDS),
        "horizon_weeks": HORIZON,
        "draws": DRAWS,
        "grid": [GRID[0], GRID[-1], 0.1],
    }
    write_rule(RULE_V3_DIR, tables["R3"], pops["lstm"], provenance_pop, provenance_table)
    write_rule(MA13_RULE_DIR, tables["MA13-R3"], pops["ma13"], provenance_pop, provenance_table)
    rng = np.random.default_rng(SEED + 10)
    fresh = [r for s in by_group["F"] for r in records_for(s, models, rule_v2, pops, rng)]
    summary = summarise(dev, fresh, tables, rule_v2, pops["lstm"], ids)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8", newline="\n")
    REPORT.write_text(render(summary, None), encoding="utf-8", newline="\n")
    return summary


def apply_v3() -> None:
    """Copy the R3 rule and its population record over the served band file."""
    for name in ("population_errors.json", "band_inflation.json"):
        shutil.copyfile(RULE_V3_DIR / name, BAND_FILE.parent / name)
    load_band_rule.cache_clear()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Engine v3 band candidate R3.")
    parser.add_argument("step", choices=("fit", "decide"))
    parser.add_argument("--synthetic", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--apply", action="store_true", help="serve R3 if every criterion holds")
    args = parser.parse_args(argv)
    if args.step == "fit":
        summary = fit(args.synthetic)
        print(json.dumps(summary["decision_inputs"], indent=1))  # noqa: T201
        return
    summary = json.loads(RESULTS.read_text(encoding="utf-8"))
    outcome = json.loads(OUTCOME_GATE.read_text(encoding="utf-8"))
    verdict = decide(summary["decision_inputs"], outcome)
    summary["verdict"] = verdict
    RESULTS.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8", newline="\n")
    REPORT.write_text(render(summary, verdict, outcome), encoding="utf-8", newline="\n")
    print(json.dumps(verdict, indent=1))  # noqa: T201
    if args.apply and verdict["serve"]:
        apply_v3()
        print(f"R3 copied to {BAND_FILE.parent}")  # noqa: T201


if __name__ == "__main__":
    main()
