"""Check the SERVED stack against the evaluation (plan P4, task C6):

    cd backend && uv run python -m ml.engine1_eval.serving_check

1. The ONNX network that the API serves reproduces the scores the evaluation recorded for it.
2. How well calibrated the served forecast is: for each origin, the user's own error record is
   built from history only (exactly as in production), simulated 13-week totals are drawn, and the
   realised total is compared with them. Reported per dataset and kind: bias of the median and
   the share of outcomes inside the 80% band, with and without engine v2's single widening factor
   (v3 widens by history length: `ml.engine1_eval.band_calibration`).
3. The served band rule (engine v3, R3: monthly floor, population record below 26 weeks) next to
   the v2 table and the single 1.5 factor on the same windows, on real data and on the held-out
   synthetic students (`real_band_check.py`).
Writes `reports/engine1/serving_check.md`. Latency and memory are printed, not written (they vary
from run to run), and recorded in STATUS.
"""

import argparse
import csv
import re
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

import numpy as np

from app.engines.forecasting.errors import rolling_error_paths, widen
from app.engines.forecasting.onnx_model import load_served
from app.engines.forecasting.service import V1_ERROR_INFLATION as ERROR_INFLATION
from app.engines.forecasting.simulate import path_bootstrap
from ml.engine1_eval import real_band_check
from ml.engine1_eval.data import Series
from ml.engine1_eval.harness import EvalConfig, evaluate_series
from ml.engine1_eval.loaders import berka, moneydata
from ml.engine1_eval.run import DEFAULT_OUT_ROOT, DataPaths, _synthetic_series, load_config

OUT = Path(__file__).resolve().parents[3] / "reports" / "engine1" / "serving_check.md"
HORIZON = 13
BAND = (10, 90)
DRAWS = 300
STRIDE = 4
MIN_HISTORY = 26


class _Scaled:
    """The served forecaster; kept as a tiny wrapper so the harness sees the usual interface."""

    def __init__(self, model) -> None:
        self._model = model
        self.name = model.name

    def forecast(self, history, horizon, start):
        return self._model.forecast(history, horizon, start)


def parity_with_evaluation(served, pairs, config, results_path: Path) -> dict:
    """Max difference between the served network's 13-week MASE and the stored evaluation rows."""
    if not results_path.exists():
        return {"checked": 0, "note": "no stored evaluation results on this machine"}
    stored = {}
    with results_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["model"] == "lstm" and row["history_limit"] == "52":
                stored[(row["series_id"], row["kind"], int(row["origin"]))] = float(row["mase_13"])
    cutoff = pairs[0]["spend"].start + timedelta(weeks=config.synthetic["cutoff_week"])
    eval_config = EvalConfig(
        horizon=HORIZON, report_horizons=(1, 4, 13), min_train=config.min_train, stride=1,
        history_limit=52, first_origin_date=cutoff,
    )  # fmt: skip
    worst, checked = 0.0, 0
    for pair in pairs[:20]:
        for kind in ("spend", "income"):
            rows = evaluate_series(pair[kind], _Scaled(served.for_kind(kind)), eval_config).rows
            for row in rows:
                key = (row["series_id"], kind, row["origin"])
                if key in stored:
                    worst = max(worst, abs(stored[key] - row["mase_13"]))
                    checked += 1
    return {"checked": checked, "max_abs_mase_difference": worst}


def _calibration(series_list: list[Series], served, inflation: float, seed: int) -> list[dict]:
    rows = []
    rng = np.random.default_rng(seed)
    for s in series_list:
        model = served.for_kind(s.kind)
        for origin in range(MIN_HISTORY, len(s) - HORIZON + 1, STRIDE):
            history = s.values[:origin]
            errors = widen(rolling_error_paths(history, s.start, model), inflation)
            if len(errors) < 2:
                continue
            point = model.forecast(history, HORIZON, s.start)
            draws = np.clip(point + path_bootstrap(errors, HORIZON, DRAWS, rng), 0, None).sum(
                axis=1
            )
            actual = float(s.values[origin : origin + HORIZON].sum())
            scale = max(float(np.mean(history[-MIN_HISTORY:])) * HORIZON, 1.0)
            low, high = np.percentile(draws, BAND)
            rows.append(
                {
                    "source": s.source,
                    "kind": s.kind,
                    "bias": (float(np.median(draws)) - actual) / scale,
                    "inside": low <= actual <= high,
                }
            )
    return rows


def _summarise(rows: list[dict]) -> list[tuple]:
    out = []
    for source in sorted({r["source"] for r in rows}):
        for kind in ("spend", "income"):
            part = [r for r in rows if r["source"] == source and r["kind"] == kind]
            if part:
                out.append(
                    (source, kind, len(part), np.median([r["bias"] for r in part]),
                     np.mean([r["inside"] for r in part]))
                )  # fmt: skip
    return out


def _table(summary: list[tuple]) -> str:
    lines = [
        "| dataset | kind | origins | typical bias (median over origins) | inside P10-P90 |",
        "|---|---|---|---|---|",
    ]
    for source, kind, n, bias, inside in summary:
        lines.append(f"| {source} | {kind} | {n} | {bias:+.3f} | {inside:.2f} |")
    return "\n".join(lines)


def measure_latency_and_memory() -> str:
    """A fresh process: import the API stack, load the model, forecast a typical persona."""
    program = (
        "import ctypes, statistics, time\n"
        "from ctypes import wintypes\n"
        "from app.engines.forecasting.service import build_forecast\n"
        "from app.engines.forecasting.serving import served_forecaster\n"
        "from ml.datagen.params import load_params\n"
        "from ml.datagen.profile import generate_profile\n"
        "p = generate_profile(load_params(), 5, 3, persona='budget_conscious')\n"
        "rows = [t.as_row() for t in p.transactions]\n"
        "m = served_forecaster()\n"
        "build_forecast(rows, [], [], p.as_of, m, seed=1)\n"
        "ts = []\n"
        "for i in range(100):\n"
        "    t = time.perf_counter(); build_forecast(rows, [], [], p.as_of, m, seed=i)\n"
        "    ts.append((time.perf_counter() - t) * 1000)\n"
        "ts.sort()\n"
        "class PMC(ctypes.Structure):\n"
        "    _fields_ = [('cb', wintypes.DWORD), ('pf', wintypes.DWORD), ('peak', ctypes.c_size_t),\n"  # noqa: E501
        "                ('ws', ctypes.c_size_t)] + [(f'x{i}', ctypes.c_size_t) for i in range(6)]\n"  # noqa: E501
        "c = PMC(); c.cb = ctypes.sizeof(PMC)\n"
        "k = ctypes.WinDLL('kernel32'); k.GetCurrentProcess.restype = wintypes.HANDLE\n"
        "ps = ctypes.WinDLL('psapi')\n"
        "ps.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]\n"  # noqa: E501
        "ps.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)\n"
        "print(f'latency ms p50={statistics.median(ts):.1f} p95={ts[94]:.1f}; '\n"
        "      f'peak working set {c.peak/1e6:.0f} MB')\n"
    )
    done = subprocess.run(  # noqa: S603 - runs this repo's own interpreter on a fixed program
        [sys.executable, "-I", "-c", program],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
        check=False,
    )
    return (done.stdout or done.stderr).strip()


def build(config_name: str, previous_report: str | None = None) -> str:
    config = load_config(config_name)
    paths = DataPaths()
    served = load_served()
    _, test_pairs = _synthetic_series(config, paths)
    synthetic = [s for pair in test_pairs for s in pair.values()]
    real = list(moneydata.load_moneydata(paths.moneydata)) + list(
        berka.load_berka(
            paths.berka_account, paths.berka_trans, config.berka["min_weeks"],
            sample=(config.berka["accounts"], config.seed),
        )
    )  # fmt: skip
    parity = parity_with_evaluation(
        served, test_pairs, config, DEFAULT_OUT_ROOT / config_name / "results.csv"
    )
    plain = _summarise(_calibration([*synthetic, *real], served, 1.0, config.seed))
    widened = _summarise(_calibration([*synthetic, *real], served, ERROR_INFLATION, config.seed))
    return (
        "# Serving check: the served LSTM against the evaluation\n\n"
        "> Generated by `python -m ml.engine1_eval.serving_check` - do not edit by hand.\n\n"
        "## 1. The served network reproduces the evaluated scores\n\n"
        f"{carry_over_parity(parity, previous_report)}\n\n"
        "The ONNX files were also compared with torch on held-out windows at export time "
        "(`backend/models/engine1/v1/metadata.json`).\n\n"
        f"## 2. Calibration of the 13-week total\n\nFor each origin the user's own error record "
        f"(latest ten origins, eight-week paths) is built from history only, {DRAWS} totals are "
        "drawn, and the realised total is compared. *Bias* is (simulated median - actual) "
        "as a share of the recent level: above 0 means the forecast was too high. *Inside P10-P90* "
        "should be 0.80 if the band were calibrated.\n\n"
        f"### Recorded errors as they are (no widening)\n\n{_table(plain)}\n\n"
        f"### With the v2 widening factor ({ERROR_INFLATION})\n\n{_table(widened)}\n\n"
        "The bands are narrower than nominal, as the P4 audit predicted; the widening factor is an "
        "assumption that narrows the gap, not a calibration. Probabilities derived from the bands "
        "(P(shortfall)) are therefore more extreme than a calibrated forecast would give, which "
        "the interface must present as an estimate. Engine 2's labels use the same function, so "
        "training and serving agree.\n\n"
        "## 3. The served band rule (R3) on real data\n\n"
        "Sections 1 and 2 score the engine v2 rules. This section scores the rule served now, "
        "through the function serving uses (`real_band_check.py`; plan "
        "`refdocs/plans/2026-10-19-local-completion.md`, section 3, rule written before this "
        f"was run).\n\n{real_band_section(synthetic, real, served, config.seed)}"
    )


PARITY_LINE = re.compile(r"^(\{'checked': [1-9]\d*,.*\})$", re.MULTILINE)


def carry_over_parity(parity: dict, previous_report: str | None) -> str:
    """The parity line for section 1. The stored evaluation results are not committed, so a
    machine without them cannot re-check parity; it keeps the previous report's verified line and
    says so, rather than overwriting a result with "nothing checked"."""
    if parity.get("checked") or not previous_report:
        return str(parity)
    found = PARITY_LINE.search(previous_report)
    if not found:
        return str(parity)
    return (
        f"{found.group(1)}\n\n(This line is carried over from the previous report: the stored "
        "evaluation results are not on the machine that regenerated this one, so parity was not "
        "re-checked here.)"
    )


def real_band_section(synthetic: list[Series], real: list[Series], served, seed: int) -> str:
    rules = real_band_check.rules_under_test()
    rows = [
        row
        for s in [*synthetic, *real]
        for row in real_band_check.score_series(s, served, rules, seed)
    ]
    return real_band_check.render_section(rows)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Check the served LSTM against the evaluation.")
    parser.add_argument("--config", default="full")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    previous = args.out.read_text(encoding="utf-8") if args.out.exists() else None
    text = build(args.config, previous)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")  # noqa: T201
    print(measure_latency_and_memory())  # noqa: T201


if __name__ == "__main__":
    start = time.perf_counter()
    main()
