"""Fit the forecast band's widening by history length, and check it (WP16, change C2):

    cd backend && uv run python -m ml.engine1_eval.band_calibration [--synthetic <csv>]

v2 widened every user's error record by one factor (1.5), and the 80% band held the realised
13-week total only 46-69% of the time (`reports/engine1/serving_check.md`). This script:

1. builds, for synthetic students, exactly what serving builds at each point of their history
   (`service.error_record`: the user's own rolling error paths, or the fallback when the record is
   too short), the served LSTM's point forecast, and 300 resampled 13-week totals for every factor
   on a grid, with the same random paths for every factor;
2. FITS, per history-length bucket and series kind, the smallest factor whose band holds the real
   total at least 80% of the time - or, where no factor gets there, the factor with the best
   coverage - on DEVELOPMENT students only: students the forecast network was never trained or
   tested on and that are not in Engine 2's lockbox (indices 4,000-9,999 of the cohort, not
   divisible by ten). Widening is never forced to grow as history shrinks: on these students a
   wider band can hold the real total LESS often (draws are clipped at zero, so widening raises
   the whole simulated total), and the data decide;
3. CHECKS the result on the 60 held-out Engine 1 test students (never used for fitting), beside
   the v2 rule, and writes `backend/models/engine1/band_inflation.json` (the table the API reads)
   and `reports/engine1/band_calibration.md`.

MoneyData and Berka are not used: their downloads are blocked in the environment this was run in
(the report says so); the v2 real-data rows stay in `serving_check.md` as the earlier version.
"""

import argparse
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.engines.forecasting.bands import BAND_FILE, parse_rule
from app.engines.forecasting.onnx_model import load_served
from app.engines.forecasting.service import MIN_SERIES_WEEKS, V1_ERROR_INFLATION, error_record
from app.engines.forecasting.simulate import forecaster_for, path_bootstrap
from ml.engine1_eval.data import Series, sample_profiles
from ml.engine1_eval.loaders.synthetic import DEFAULT_PATH, load_synthetic

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "reports" / "engine1" / "band_calibration.md"
SEED = 20251228  # the Engine 1 evaluation's seed (configs/full.yaml)
EVAL_POOL, EVAL_TRAIN, EVAL_TEST = 4000, 3000, 60  # configs/full.yaml: which students it used
COHORT = 10_000
DEV_PROFILES = 300
HORIZON = 13  # weeks: the 13-week total, as in the serving check
DRAWS = 300
STRIDE = 4
TARGET = 0.80
BAND = (10, 90)
GRID = tuple(round(1.0 + 0.1 * i, 1) for i in range(51))  # 1.0 .. 6.0
BUCKETS = (MIN_SERIES_WEEKS, 26, 39, 52)  # lower edges in weeks of history; the last is open
KINDS = ("spend", "income")


@dataclass(frozen=True)
class Record:
    profile: int
    kind: str
    weeks: int
    fallback: bool
    inside: np.ndarray  # bool per GRID factor: the realised total fell inside P10-P90
    inside_recentred: np.ndarray  # the same with the record's mean error removed (C6 diagnostic)
    bias_v2: float  # (simulated median - actual) / recent level, at the v2 factor
    bias_recentred: float  # the same with the record re-centred, at the v2 factor


def dev_profiles(count: int = DEV_PROFILES, seed: int = SEED) -> list[int]:
    pool = [i for i in range(EVAL_POOL, COHORT) if i % 10 != 0]
    rng = np.random.default_rng(seed + 1)
    return sorted(int(i) for i in rng.choice(pool, size=count, replace=False))


def test_profiles(seed: int = SEED) -> list[int]:
    return sample_profiles(EVAL_POOL, seed, EVAL_TRAIN, EVAL_TEST)[1]


def bucket_of(weeks: int) -> int:
    return max(i for i, low in enumerate(BUCKETS) if weeks >= low)


def records_for(series: Series, served, rng: np.random.Generator) -> list[Record]:
    out = []
    v2_index = GRID.index(V1_ERROR_INFLATION)
    model = forecaster_for(served, series.kind)
    for origin in range(MIN_SERIES_WEEKS, len(series) - HORIZON + 1, STRIDE):
        history = series.values[:origin]
        errors, fallback = error_record(history, series.start, served, series.kind)
        point = np.clip(model.forecast(history, HORIZON, series.start), 0, None)
        sampled = path_bootstrap(errors, HORIZON, DRAWS, rng)
        centre = errors.mean() if errors.size else 0.0
        actual = float(series.values[origin : origin + HORIZON].sum())
        scale = max(float(np.mean(history[-26:])) * HORIZON, 1.0)
        inside = np.zeros(len(GRID), dtype=bool)
        recentred = np.zeros(len(GRID), dtype=bool)
        bias = bias_r = 0.0
        for i, factor in enumerate(GRID):
            spread = factor * (sampled - centre)
            for keep_centre, target in ((True, inside), (False, recentred)):
                totals = np.clip(point + (centre if keep_centre else 0.0) + spread, 0, None)
                totals = totals.sum(axis=1)
                low, high = np.percentile(totals, BAND)
                target[i] = low <= actual <= high
                if i == v2_index:
                    gap = (float(np.median(totals)) - actual) / scale
                    if keep_centre:
                        bias = gap
                    else:
                        bias_r = gap
        out.append(Record(int(series.series_id.split("-")[1]), series.kind, origin, fallback,
                          inside, recentred, bias, bias_r))  # fmt: skip
    return out


def collect(path: Path, profiles: Iterable[int], served, seed: int) -> list[Record]:
    rng = np.random.default_rng(seed)
    records: list[Record] = []
    for series in load_synthetic(path, profile_ids=set(profiles)):
        records.extend(records_for(series, served, rng))
    return records


def coverage(records: Sequence[Record], factor_of, attr: str = "inside") -> float | None:
    if not records:
        return None
    return float(np.mean([getattr(r, attr)[GRID.index(factor_of(r))] for r in records]))


def fit(records: Sequence[Record], attr: str = "inside") -> dict[str, list[float]]:
    """Per (bucket, kind): the smallest factor whose development coverage reaches TARGET, else
    the factor with the best coverage (ties: the smallest)."""
    table: dict[str, list[float]] = {}
    for kind in KINDS:
        factors = []
        for b in range(len(BUCKETS)):
            part = [r for r in records if r.kind == kind and bucket_of(r.weeks) == b]
            if not part:
                factors.append(GRID[0])
                continue
            rates = np.mean([getattr(r, attr) for r in part], axis=0)
            reaching = [i for i, rate in enumerate(rates) if rate >= TARGET]
            factors.append(GRID[reaching[0] if reaching else int(np.argmax(rates))])
        table[kind] = factors
    return table


def _rule_json(table: dict[str, list[float]], dev: list[Record], dev_ids: list[int]) -> dict:
    rule = {
        "version": "2",
        "replaces": f"one factor of {V1_ERROR_INFLATION} for every user (engine version v2)",
        "target_coverage": TARGET,
        "buckets": [
            {"min_weeks": low, "spend": table["spend"][b], "income": table["income"][b]}
            for b, low in enumerate(BUCKETS)
        ],
        "fitted_on": {
            "students": len(dev_ids),
            "rule": "cohort indices 4000-9999 not divisible by 10 (never used by the Engine 1 "
            "evaluation or training, never in Engine 2's lockbox), seeded draw",
            "origins_per_kind": len(dev) // len(KINDS),
            "horizon_weeks": HORIZON,
            "draws": DRAWS,
            "grid": [GRID[0], GRID[-1], 0.1],
        },
        "generated_by": "python -m ml.engine1_eval.band_calibration",
    }
    parse_rule(rule)  # the API must be able to read what is written
    return rule


def _table_rows(records: Sequence[Record], rule_of) -> list[str]:
    lines = []
    for kind in KINDS:
        for b, low in enumerate(BUCKETS):
            part = [r for r in records if r.kind == kind and bucket_of(r.weeks) == b]
            high = f"{BUCKETS[b + 1] - 1}" if b + 1 < len(BUCKETS) else "+"
            v2 = coverage(part, lambda _: V1_ERROR_INFLATION)
            v3 = coverage(part, rule_of)
            factor = rule_of(part[0]) if part else None
            lines.append(
                f"| {kind} | {low}-{high} | {len(part)} | {v2:.2f} | {factor} | {v3:.2f} |"
                if part
                else f"| {kind} | {low}-{high} | 0 | - | - | - |"
            )
        every = [r for r in records if r.kind == kind]
        lines.append(
            f"| {kind} | all | {len(every)} | {coverage(every, lambda _: V1_ERROR_INFLATION):.2f}"
            f" | | {coverage(every, rule_of):.2f} |"
        )
    return lines


def _recentred_rows(test: Sequence[Record], table_r: dict[str, list[float]]) -> list[str]:
    lines = []
    for kind in KINDS:
        for b, low in enumerate(BUCKETS):
            part = [r for r in test if r.kind == kind and bucket_of(r.weeks) == b]
            if not part:
                continue
            high = f"{BUCKETS[b + 1] - 1}" if b + 1 < len(BUCKETS) else "+"
            factor = table_r[kind][b]
            plain = coverage(part, lambda _: V1_ERROR_INFLATION, "inside_recentred")
            fitted = coverage(part, lambda _, f=factor: f, "inside_recentred")
            lines.append(f"| {kind} | {low}-{high} | {plain:.2f} | {factor} | {fitted:.2f} |")
    return lines


def report(
    dev: list[Record],
    test: list[Record],
    table: dict[str, list[float]],
    source: str,
    table_r: dict[str, list[float]] | None = None,
) -> str:
    def rule_of(r: Record) -> float:
        return table[r.kind][bucket_of(r.weeks)]

    table_r = table_r or fit(dev, "inside_recentred")
    bias_r = {k: np.median([r.bias_recentred for r in test if r.kind == k]) for k in KINDS}

    fallback_share = np.mean([r.fallback for r in test]) if test else 0.0
    header = [
        "| series | weeks of history | origins | inside P10-P90, v2 (x1.5) | v3 factor | "
        "inside P10-P90, v3 |",
        "|---|---|---|---|---|---|",
    ]
    bias = {k: np.median([r.bias_v2 for r in test if r.kind == k]) for k in KINDS}
    return "\n".join(
        [
            "# Band calibration: widening the error record by history length (WP16, C2)",
            "",
            "> Generated by `python -m ml.engine1_eval.band_calibration` - do not edit by hand.",
            "",
            "Each row is a point in a synthetic student's history: what serving would build there "
            "(the user's own error paths, or the fallback when the record is too short), the "
            f"served LSTM's forecast, and {DRAWS} resampled {HORIZON}-week totals. *Inside "
            "P10-P90* is the share of points where the real total fell inside the band; it should "
            f"be {TARGET:.2f}. v2 widened every record by {V1_ERROR_INFLATION}; v3 uses the "
            "factor fitted for the history length and series.",
            "",
            f"## Held-out check: the {len(test) and len({r.profile for r in test})} Engine 1 "
            "test students (never used for fitting)",
            "",
            *header,
            *_table_rows(test, rule_of),
            "",
            f"Share of held-out points whose record came from the fallback (too short to score "
            f"the model): {fallback_share:.2f}. Median bias of the simulated median at the v2 "
            f"factor (as a share of the recent level; above 0 = too high): spend "
            f"{bias['spend']:+.3f}, income {bias['income']:+.3f}. Widening does not move the "
            "centre, so this bias is unchanged by v3.",
            "",
            "## Diagnostic, not served: the same band with the user's mean error removed (C6)",
            "",
            "Serving centres the simulated paths on the user's own record, so a level bias the "
            "model has shown is carried into the future paths. Removing it (re-centring the "
            "record on zero) is what the C6 bias-term sensitivity tests on the labels "
            "(`reports/engine2/README.md`). Factors below are fitted the same way, on the "
            "development students; coverage is on the held-out students.",
            "",
            "| series | weeks of history | inside, re-centred x1.5 | fitted factor | inside, "
            "re-centred and fitted |",
            "|---|---|---|---|---|",
            *_recentred_rows(test, table_r),
            "",
            f"Median bias of the simulated median when re-centred (x1.5): spend "
            f"{bias_r['spend']:+.3f}, income {bias_r['income']:+.3f}.",
            "",
            f"## Development fit: {len({r.profile for r in dev})} students",
            "",
            *header,
            *_table_rows(dev, rule_of),
            "",
            "## The table the API reads (`backend/models/engine1/band_inflation.json`)",
            "",
            "| weeks of history from | spend | income |",
            "|---|---|---|",
            *[
                f"| {low} | {table['spend'][b]} | {table['income'][b]} |"
                for b, low in enumerate(BUCKETS)
            ],
            "",
            "## Limits",
            "",
            f"- Synthetic students only ({source}). MoneyData and Berka could not be downloaded "
            "in this environment (network policy), so no real-data coverage is claimed for v3; "
            "the v2 real-data rows stay in `serving_check.md` as the earlier version.",
            "- The cohort is 78 weeks long, so the last bucket is fitted on 52-65 weeks of history "
            "and applied to anything longer.",
            "- Coverage is of the 13-week total. P(shortfall) also depends on the centre of the "
            "band, which widening does not correct (the bias line above).",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fit and check the band widening by history.")
    parser.add_argument("--synthetic", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--dev-profiles", type=int, default=DEV_PROFILES)
    parser.add_argument("--out-json", type=Path, default=BAND_FILE)
    parser.add_argument("--out-report", type=Path, default=REPORT)
    args = parser.parse_args(argv)
    served = load_served()
    dev_ids = dev_profiles(args.dev_profiles)
    dev = collect(args.synthetic, dev_ids, served, SEED)
    test = collect(args.synthetic, test_profiles(), served, SEED + 2)
    table = fit(dev)
    args.out_json.write_text(
        json.dumps(_rule_json(table, dev, dev_ids), indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    source = "data/synthetic/weekly_series.csv, regenerated by `ml.datagen.export`"
    args.out_report.write_text(report(dev, test, table, source), encoding="utf-8", newline="\n")
    print(f"wrote {args.out_json} and {args.out_report}")  # noqa: T201
    print(json.dumps(table))  # noqa: T201


if __name__ == "__main__":
    main()
