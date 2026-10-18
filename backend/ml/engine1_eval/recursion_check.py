"""How far the served LSTM's recursive continuation drifts beyond 13 weeks (evaluation only):

    cd backend && uv run python -m ml.engine1_eval.recursion_check [--synthetic <csv>]

The served network forecasts 13 weeks; beyond that it is fed its own forecast
(`onnx_model.OnnxLstm.forecast`), and a long plan's label depends on that continuation (ASSUMED
11, ADR D-36). For the outcome check's development students (`outcome_check.outcome_profiles`),
at origins 17 and 26 weeks into each ledger, this compares the error of the CUMULATIVE total at
13, 26, 39 and 52 weeks with two benchmarks run the same way: naive (repeat the last week) and
MA13 (repeat the mean of the last 13 weeks). The error is (forecast total - realised total) /
(recent level x weeks), where the recent level is the mean of the last 26 weeks of history: below
0 means the forecast was too low. Spending and income are reported separately.

It fits, chooses and changes nothing that is served. Writes `reports/engine1/recursion_check.md`
and `reports/engine1/tables/recursion_check.csv`.
"""

import argparse
import csv
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from app.engines.forecasting.serving import served_forecaster
from app.engines.forecasting.simulate import Forecaster, forecaster_for
from ml.engine1_eval.loaders.synthetic import DEFAULT_PATH, load_synthetic
from ml.engine1_eval.outcome_check import OUTCOME_PROFILES, outcome_profiles

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "reports" / "engine1" / "recursion_check.md"
TABLE = ROOT / "reports" / "engine1" / "tables" / "recursion_check.csv"
ORIGINS = (17, 26)  # weeks of history; 26 + 52 = the cohort's 78 weeks
HORIZONS = (13, 26, 39, 52)
LEVEL_WEEKS = 26
MODELS = ("lstm", "ma13", "naive")
LABELS = {
    "lstm": "served LSTM (recursive)",
    "ma13": "MA13 (benchmark)",
    "naive": "naive (benchmark)",
}
KINDS = ("spend", "income")


@dataclass(frozen=True)
class Errors:
    profile: int
    kind: str
    origin: int
    model: str
    errors: tuple[float, ...]  # one per HORIZONS


def scaled_errors(
    values: np.ndarray,
    start: date,
    origin: int,
    forecaster: Forecaster,
    horizons: Sequence[int] = HORIZONS,
) -> list[float] | None:
    """Cumulative-total error at each horizon as a share of the recent level, or None when the
    recent level is 0 (no scale to measure against)."""
    history = np.asarray(values[:origin], dtype=float)
    level = float(np.mean(history[-LEVEL_WEEKS:]))
    if level <= 0:
        return None
    longest = max(horizons)
    forecast = np.clip(forecaster.forecast(history, longest, start), 0, None)
    actual = np.asarray(values[origin : origin + longest], dtype=float)
    if len(actual) < longest:
        raise ValueError(f"the series has {len(actual)} weeks after week {origin}, need {longest}")
    return [float((forecast[:h].sum() - actual[:h].sum()) / (level * h)) for h in horizons]


def collect(
    path: Path, profiles: Iterable[int], models: Mapping[str, Forecaster]
) -> tuple[list[Errors], dict[tuple[str, int], int]]:
    records: list[Errors] = []
    skipped: dict[tuple[str, int], int] = {}
    for series in load_synthetic(path, profile_ids=set(profiles)):
        profile = int(series.series_id.split("-")[1])
        for origin in ORIGINS:
            for name, model in models.items():
                errors = scaled_errors(
                    series.values, series.start, origin, forecaster_for(model, series.kind)
                )
                if errors is None:
                    if name == MODELS[0]:
                        skipped[(series.kind, origin)] = skipped.get((series.kind, origin), 0) + 1
                    continue
                records.append(Errors(profile, series.kind, origin, name, tuple(errors)))
    return records, skipped


def summarise(errors: np.ndarray) -> dict[str, float]:
    errors = np.asarray(errors, dtype=float)
    return {
        "median": float(np.median(errors)),
        "mae": float(np.mean(np.abs(errors))),
        "median_abs": float(np.median(np.abs(errors))),
    }


def _matrix(records: Sequence[Errors], kind: str, origin: int, model: str) -> np.ndarray:
    part = sorted(
        (r for r in records if r.kind == kind and r.origin == origin and r.model == model),
        key=lambda r: r.profile,
    )
    return np.array([r.errors for r in part], dtype=float).reshape(len(part), len(HORIZONS))


def summary_rows(records: Sequence[Errors]) -> list[dict]:
    rows = []
    for kind in KINDS:
        for origin in ORIGINS:
            lstm = _matrix(records, kind, origin, "lstm")
            ma13 = _matrix(records, kind, origin, "ma13")
            for model in MODELS:
                values = _matrix(records, kind, origin, model)
                if not len(values):
                    continue
                for i, h in enumerate(HORIZONS):
                    beats = None
                    if model == "lstm" and len(lstm) == len(ma13):
                        beats = float(np.mean(np.abs(lstm[:, i]) < np.abs(ma13[:, i])))
                    rows.append(
                        {
                            "kind": kind,
                            "origin_weeks": origin,
                            "model": model,
                            "horizon_weeks": h,
                            "series": len(values),
                            **summarise(values[:, i]),
                            "share_lstm_beats_ma13": beats,
                        }
                    )
    return rows


def render(
    records: Sequence[Errors], skipped: Mapping[tuple[str, int], int], ids: Sequence[int]
) -> str:
    rows = summary_rows(records)
    lines = [
        "# Recursion check: the served LSTM beyond 13 weeks against naive and MA13",
        "",
        "> Generated by `python -m ml.engine1_eval.recursion_check` - do not edit by hand.",
        "",
        f"{len(ids)} synthetic development students (the outcome check's students: never Engine "
        "2's lockbox, the Engine 1 test students, the fresh-check students or the band table's "
        "fitting students). Evaluation only: nothing was fitted, chosen or changed.",
        "",
        f"At origins {' and '.join(str(o) for o in ORIGINS)} weeks into each ledger, each model "
        f"forecasts {max(HORIZONS)} weeks from the history before the origin; the served LSTM "
        "is continued recursively beyond its trained 13 weeks, exactly as serving does. The "
        "error at a horizon is (forecast total - realised total) / (recent level x weeks), the "
        f"recent level being the mean of the last {LEVEL_WEEKS} weeks of history: **below 0 = "
        "the forecast was too low**. *Median* is the median signed error, *MAE* the mean "
        "absolute error, *median |e|* the median absolute error, and *LSTM beats MA13* the "
        "share of series where the LSTM's absolute error is the smaller.",
        "",
    ]
    header = "| model | " + " | ".join(f"{h} weeks: median | MAE | median abs" for h in HORIZONS)
    for kind in KINDS:
        for origin in ORIGINS:
            part = [r for r in rows if r["kind"] == kind and r["origin_weeks"] == origin]
            if not part:
                continue
            series = part[0]["series"]
            lines += [
                f"## {'Spending' if kind == 'spend' else 'Income'}, origin at week {origin}",
                "",
                f"{series} series; {skipped.get((kind, origin), 0)} left out (recent level 0).",
                "",
                header + " |",
                "|---|" + "---|---|---|" * len(HORIZONS),
            ]
            for model in MODELS:
                cells = [r for r in part if r["model"] == model]
                lines.append(
                    f"| {LABELS[model]} | "
                    + " | ".join(
                        f"{c['median']:+.3f} | {c['mae']:.3f} | {c['median_abs']:.3f}"
                        for c in cells
                    )
                    + " |"
                )
            beats = [r for r in part if r["model"] == "lstm"]
            lines += [
                "",
                "LSTM beats MA13 (share of series): "
                + "; ".join(
                    f"{r['horizon_weeks']} weeks {r['share_lstm_beats_ma13']:.3f}" for r in beats
                )
                + ".",
                "",
            ]
    lines += [
        "## Limits",
        "",
        "- Synthetic students only; every student shares one calendar, so each origin is one "
        "point in the year.",
        "- The cohort is 78 weeks long, so a 52-week horizon is possible only from origins up "
        "to week 26: the long horizons are measured on short histories.",
        "- Income is total income, not the residual income serving forecasts after confirmed "
        "recurring items.",
        "",
    ]
    return "\n".join(lines)


def write_csv(rows: Sequence[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {k: (round(v, 6) if isinstance(v, float) else v) for k, v in row.items()}
            )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Recursive LSTM against benchmarks to 52 weeks.")
    parser.add_argument("--synthetic", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--profiles", type=int, default=OUTCOME_PROFILES)
    parser.add_argument("--out-report", type=Path, default=REPORT)
    parser.add_argument("--out-table", type=Path, default=TABLE)
    args = parser.parse_args(argv)
    began = time.perf_counter()
    ids = outcome_profiles(args.profiles)
    records, skipped = collect(args.synthetic, ids, {m: served_forecaster(m) for m in MODELS})
    args.out_report.write_text(render(records, skipped, ids), encoding="utf-8", newline="\n")
    write_csv(summary_rows(records), args.out_table)
    seconds = time.perf_counter() - began
    print(f"wrote {args.out_report}, {args.out_table}: {len(records)} rows, {seconds:.1f} s")  # noqa: T201


if __name__ == "__main__":
    main()
