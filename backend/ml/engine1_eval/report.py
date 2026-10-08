"""Engine 1 report: `python -m ml.engine1_eval.report --config small|full` (plan P3, task B12).

Reads the stored results of a run and writes `reports/engine1/` (tables, figures, README,
`selection.json`). The model to serve is chosen mechanically by the rule fixed in the execution
doc before any result existed (ADR D-06); nothing here can change the rule after seeing numbers.
Benchmarks are in every table, and results are reported even when they are unflattering.
"""

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ml.engine1_eval.run import DEFAULT_OUT_ROOT  # noqa: E402
from ml.engine1_eval.stats import (  # noqa: E402
    bootstrap_median_ci,
    friedman_nemenyi,
    holm_adjust,
    wilcoxon_paired,
)

DEFAULT_REPORT_DIR = Path(__file__).resolve().parents[3] / "reports" / "engine1"
BENCHMARKS = ("naive", "ma4", "ma13")
LITERATURE = ("arima", "prophet", "lstm")
ALL_SOURCES = ("synthetic", "moneydata", "berka")
SIGNIFICANCE = 0.05
MATERIAL_MASE_DIFFERENCE = 0.02  # a benchmark must lead by at least this much to override D-05
DECIMALS = 4
FIGURE_DPI = 110
PNG_METADATA = {"Software": None}
SEED = 20251228


@dataclass(frozen=True)
class Selection:
    best_literature: str
    best_benchmark: str
    served: str
    branch: str  # "literature" | "benchmark"
    p_value: float
    median_difference: float  # best literature minus best benchmark; positive = literature worse
    ci_low: float
    ci_high: float
    n_series: int
    metric: dict[str, float]


def select_model(scores: pd.DataFrame) -> Selection:
    """Apply the D-06 rule to per-series mean MASE (columns source, series_id, kind, model, mase).

    Metric per model: mean over sources of the mean over that source's series, so one big source
    cannot drown a small real one. Serve the best literature candidate unless the best benchmark
    beats it by at least MATERIAL_MASE_DIFFERENCE with a Holm-adjusted Wilcoxon p < 0.05.
    """
    per_source = scores.groupby(["model", "source"])["mase"].mean().reset_index()
    metric = per_source.groupby("model")["mase"].mean().to_dict()
    literature = [m for m in metric if m in LITERATURE]
    benchmarks = [m for m in metric if m in BENCHMARKS]
    if not literature:
        raise ValueError("no literature candidate (arima, prophet, lstm) in the results")
    if not benchmarks:
        raise ValueError("no benchmark (naive, ma4, ma13) in the results")
    best_l = min(literature, key=lambda m: metric[m])
    best_b = min(benchmarks, key=lambda m: metric[m])

    wide = scores.pivot_table(index=["source", "series_id", "kind"], columns="model", values="mase")
    paired = wide[[best_l, best_b]].dropna()
    result = wilcoxon_paired(paired[best_l].to_numpy(), paired[best_b].to_numpy())
    (adjusted,) = holm_adjust([result.p_value])
    low, high = bootstrap_median_ci(paired[best_l].to_numpy() - paired[best_b].to_numpy(), SEED)
    benchmark_wins = (
        result.median_difference >= MATERIAL_MASE_DIFFERENCE and adjusted < SIGNIFICANCE
    )
    return Selection(
        best_literature=best_l,
        best_benchmark=best_b,
        served=best_b if benchmark_wins else best_l,
        branch="benchmark" if benchmark_wins else "literature",
        p_value=adjusted,
        median_difference=result.median_difference,
        ci_low=low,
        ci_high=high,
        n_series=len(paired),
        metric={m: float(v) for m, v in metric.items()},
    )


def _load(run_dir: Path) -> dict:
    read = lambda name: pd.read_csv(run_dir / name, keep_default_na=True)  # noqa: E731
    results = read("results.csv")
    results["history_limit"] = results["history_limit"].astype("string").fillna("")
    margin = read("margin.csv")
    margin["history_limit"] = margin["history_limit"].astype("string").fillna("")
    timing = read("timing.csv")
    timing["history_limit"] = timing["history_limit"].astype("string").fillna("")
    return {
        "results": results,
        "margin": margin,
        "timing": timing,
        "failures": read("failures.csv"),
        "run": json.loads((run_dir / "run.json").read_text(encoding="utf-8")),
    }


def _decision_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Real-data rows plus the synthetic rows at the longest history shown to the models."""
    numeric = pd.to_numeric(frame["history_limit"], errors="coerce")
    longest = numeric.max()
    keep = frame["history_limit"].eq("") | numeric.eq(longest)
    return frame[keep]


def _round(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.round(DECIMALS)


def _write(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _round(frame).to_csv(path, index=False, lineterminator="\n")


def _tables(data: dict, horizon: int, out: Path) -> dict[str, pd.DataFrame]:
    results = data["results"]
    decision = _decision_rows(results)
    mase_cols = [c for c in results.columns if c.startswith("mase_")]
    pooled = (
        results.groupby(["source", "history_limit", "kind", "model"])
        .agg(
            **{c: (c, "mean") for c in mase_cols},
            median_mase=(f"mase_{horizon}", "median"),
            series=("series_id", "nunique"),
            origins=("origin", "count"),
        )
        .reset_index()
    )
    coverage = (
        decision.groupby(["source", "model"])
        .agg(
            coverage=(f"coverage_{horizon}", "mean"),
            width=(f"width_{horizon}", "mean"),
            share_with_interval=(f"coverage_{horizon}", lambda s: s.notna().mean()),
        )
        .reset_index()
    )
    margin_cols = [c for c in data["margin"].columns if c.startswith("margin_")]
    margin = (
        _decision_rows(data["margin"])
        .groupby(["source", "model"])[margin_cols]
        .mean()
        .reset_index()
    )
    synthetic = results[results["source"] == "synthetic"]
    by_history = (
        synthetic.groupby(["history_limit", "model"])[f"mase_{horizon}"].mean().reset_index()
    )
    by_history["history_limit"] = pd.to_numeric(by_history["history_limit"])
    by_history = by_history.sort_values(["history_limit", "model"])
    timing = data["timing"].copy()
    timing["ms_per_origin"] = timing["seconds"] / timing["origins"].clip(lower=1) * 1000
    tables = {
        "pooled_mase": pooled.sort_values(["source", "history_limit", "kind", "model"]),
        "coverage": coverage.sort_values(["source", "model"]),
        "margin": margin.sort_values(["source", "model"]),
        "by_history": by_history,
        "timing": timing.sort_values(["source", "history_limit", "model"]),
    }
    for name, frame in tables.items():
        _write(frame, out / "tables" / f"{name}.csv")
    return tables


def _series_scores(results: pd.DataFrame, horizon: int) -> pd.DataFrame:
    decision = _decision_rows(results)
    scores = (
        decision.groupby(["source", "series_id", "kind", "model"])[f"mase_{horizon}"]
        .mean()
        .reset_index()
        .rename(columns={f"mase_{horizon}": "mase"})
    )
    return scores.dropna()


def _friedman_table(scores: pd.DataFrame, out: Path) -> pd.DataFrame:
    rows = []
    for (source, kind), group in scores.groupby(["source", "kind"]):
        wide = group.pivot_table(index="series_id", columns="model", values="mase").dropna()
        if wide.shape[1] < 3 or wide.shape[0] < 5:
            continue
        result = friedman_nemenyi(wide.to_numpy().T, list(wide.columns))
        rows.append(
            {
                "source": source,
                "kind": kind,
                "series": wide.shape[0],
                "friedman_p": result.p_value,
                "critical_difference": result.critical_difference,
                "mean_ranks": "; ".join(
                    f"{m}={r:.2f}" for m, r in sorted(result.mean_ranks.items())
                ),
                "significant_pairs": "; ".join(f"{a}<>{b}" for a, b in result.significant_pairs),
            }
        )
    frame = pd.DataFrame(
        rows,
        columns=[
            "source",
            "kind",
            "series",
            "friedman_p",
            "critical_difference",
            "mean_ranks",
            "significant_pairs",
        ],
    )
    _write(frame, out / "tables" / "friedman.csv")
    return frame


def _pairwise_table(scores: pd.DataFrame, selection: Selection, out: Path) -> pd.DataFrame:
    wide = scores.pivot_table(index=["source", "series_id", "kind"], columns="model", values="mase")
    rows = []
    for model in wide.columns:
        if model == selection.best_benchmark:
            continue
        pair = wide[[model, selection.best_benchmark]].dropna()
        if len(pair) < 5:
            continue
        diffs = pair[model].to_numpy() - pair[selection.best_benchmark].to_numpy()
        test = wilcoxon_paired(pair[model].to_numpy(), pair[selection.best_benchmark].to_numpy())
        low, high = bootstrap_median_ci(diffs, SEED)
        rows.append(
            {
                "model": model,
                "against": selection.best_benchmark,
                "series": len(pair),
                "median_mase_difference": test.median_difference,
                "ci_low": low,
                "ci_high": high,
                "p_value": test.p_value,
            }
        )
    frame = pd.DataFrame(rows)
    if len(frame):
        frame["p_holm"] = holm_adjust(frame["p_value"].tolist())
    _write(frame, out / "tables" / "pairwise.csv")
    return frame


def _save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=FIGURE_DPI, metadata=PNG_METADATA, bbox_inches="tight")
    plt.close(fig)


def _figures(
    tables: dict[str, pd.DataFrame], selection: Selection, horizon: int, out: Path
) -> None:
    pooled = tables["pooled_mase"]
    decision = pooled[
        (pooled["history_limit"] == "")
        | (
            pd.to_numeric(pooled["history_limit"], errors="coerce")
            == pd.to_numeric(pooled["history_limit"], errors="coerce").max()
        )
    ]
    wide = decision.groupby(["source", "model"])[f"mase_{horizon}"].mean().unstack("source")
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    wide.plot.bar(ax=ax)
    ax.axhline(1.0, color="#94a3b8", linewidth=1, linestyle="--")
    ax.set_ylabel(f"Mean MASE, {horizon}-week horizon")
    ax.set_title("Forecast error by model and dataset (1.0 = the in-sample naive error)")
    ax.legend(title="dataset")
    _save(fig, out / "figures" / "mase_by_model.png")

    history = tables["by_history"]
    if len(history):
        fig, ax = plt.subplots(figsize=(6.5, 3.6))
        for model, group in history.groupby("model"):
            ax.plot(group["history_limit"], group[f"mase_{horizon}"], marker="o", label=model)
        ax.set_xlabel("Weeks of history shown to the model")
        ax.set_ylabel(f"Mean MASE, {horizon}-week horizon")
        ax.set_title("Synthetic cohort: error against history length")
        ax.legend()
        _save(fig, out / "figures" / "mase_by_history.png")

    coverage = tables["coverage"].pivot(index="model", columns="source", values="coverage")
    fig, ax = plt.subplots(figsize=(7, 3.6))
    coverage.plot.bar(ax=ax)
    ax.axhline(0.8, color="#94a3b8", linewidth=1, linestyle="--")
    ax.set_ylabel("Interval coverage (nominal 0.80)")
    ax.set_title("Prediction interval coverage")
    _save(fig, out / "figures" / "coverage.png")


def _md(frame: pd.DataFrame) -> str:
    frame = frame.round(DECIMALS).fillna("")
    head = (
        "| "
        + " | ".join(map(str, frame.columns))
        + " |\n|"
        + "|".join("---" for _ in frame.columns)
        + "|\n"
    )
    body = "".join("| " + " | ".join(str(v) for v in row) + " |\n" for row in frame.to_numpy())
    return head + body


CAVEATS = """\
## Read this before trusting any number

- **The synthetic cohort is circular by construction.** The generator and these forecasters have
  the same author. The weekly series carries AR(1) drift, a payday-week lift, exam-week dips and
  outlier weeks (see `reports/datagen/README.md`); a model that happens to match them gains over
  a real series. That is why MoneyData and Berka are reported separately and weighted equally.
- **Real data is not Malaysian students.** MoneyData is one UK adult's account; its weekly spend
  averages about GBP 1,170, so it probably includes movements between the owner's own accounts.
  Berka is Czech bank accounts from 1993-1998. Both are benchmarks only (D-25).
- **The global LSTM is trained on synthetic data only** and applied zero-shot to MoneyData and
  Berka. Pre-training it on Berka (D-25) was not done in this run.
- **Prediction intervals** are per-step empirical quantiles of the model's own earlier errors, the
  same for every model. The product's 4-week moving-block bootstrap, which simulates whole paths,
  is built in P4; it is not needed to compare marginal coverage.
- **Income is evaluated as total weekly income.** Splitting it into confirmed and unconfirmed parts
  waits for recurring detection (P4).
- **Evaluated series are a seeded sample**, the same for every model, because Prophet and AutoARIMA
  are refitted at every origin. The synthetic origins start at the cutoff week so the global LSTM
  is never tested on weeks it was trained on.
- **Windows and settings are fixed, not tuned on test origins:** moving averages of 4 and 13 weeks,
  AutoARIMA with season length 1, Prophet with yearly seasonality only above two years of history.
"""


def render_readme(
    data: dict,
    selection: Selection,
    tables: dict[str, pd.DataFrame],
    friedman: pd.DataFrame,
    pairwise: pd.DataFrame,
    horizon: int,
) -> str:
    config = data["run"]["config"]
    sources = sorted(set(data["results"]["source"]))
    missing = [s for s in ALL_SOURCES if s not in sources]
    availability = f"Datasets in this run: {', '.join(sources)}."
    if missing:
        availability += f" Not available or not run: {', '.join(missing)}."
    s = selection
    headline = (
        f"**Served model: `{s.served}`** (rule branch: {s.branch}). "
        f"Best literature candidate `{s.best_literature}` "
        f"(metric {s.metric[s.best_literature]:.4f}); "
        f"best benchmark `{s.best_benchmark}` (metric {s.metric[s.best_benchmark]:.4f}). "
        f"Median per-series MASE difference (literature minus benchmark) "
        f"{s.median_difference:+.4f}, 95% CI [{s.ci_low:+.4f}, {s.ci_high:+.4f}], "
        f"Holm-adjusted Wilcoxon p = {s.p_value:.4g} over {s.n_series} series."
    )
    rule = (
        "Rule (ADR D-06, fixed before any result): serve the best literature candidate (ARIMA, "
        f"Prophet, LSTM) by mean MASE at {horizon} weeks, averaged over datasets with equal "
        f"weight, unless the best benchmark beats it by at least {MATERIAL_MASE_DIFFERENCE} MASE "
        f"with a Holm-adjusted Wilcoxon p < {SIGNIFICANCE}, in which case the benchmark is "
        "served and that is the finding."
    )
    decision = pd.DataFrame(sorted(s.metric.items()), columns=["model", "decision_metric"])
    command = f"uv run python -m ml.engine1_eval.run --config {config['name']}"
    regenerate = (
        "## Regenerate\n\n```\ncd backend\n"
        f"{command}\nuv run python -m ml.engine1_eval.report --config {config['name']}\n```\n"
    )
    sections = [
        "# Engine 1 evaluation: which forecaster to serve\n",
        "> Generated by `python -m ml.engine1_eval.report` - do not edit by hand.\n",
        f"Run `{config['name']}`, seed {config['seed']}, horizon {horizon} weeks, "
        f"candidates {', '.join(config['models'])}.\n",
        f"{availability} Series failures recorded: {len(data['failures'])} "
        "(`failures.csv` in the run directory).\n",
        f"## Decision\n\n{rule}\n\n{headline}\n",
        _md(decision),
        "![MASE by model](figures/mase_by_model.png)\n",
        "## Against the best benchmark\n",
        _md(pairwise) if len(pairwise) else "Not enough paired series.\n",
        "## Friedman and Nemenyi (lower rank is better)\n",
        _md(friedman) if len(friedman) else "Not enough series.\n",
        "## Error by dataset, kind and model\n",
        _md(tables["pooled_mase"]),
        "![MASE by history](figures/mase_by_history.png)\n",
        "## Interval coverage\n",
        _md(tables["coverage"]),
        "![Coverage](figures/coverage.png)\n",
        "## Cumulative-margin error (scaled)\n",
        _md(tables["margin"]),
        "## Cost\n",
        _md(tables["timing"]),
        CAVEATS,
        regenerate,
    ]
    return "\n".join(sections)


def build_report(run_dir: Path, out_dir: Path) -> Selection:
    data = _load(run_dir)
    horizon = int(data["run"]["config"]["horizon"])
    tables = _tables(data, horizon, out_dir)
    scores = _series_scores(data["results"], horizon)
    selection = select_model(scores)
    friedman = _friedman_table(scores, out_dir)
    pairwise = _pairwise_table(scores, selection, out_dir)
    _figures(tables, selection, horizon, out_dir)
    (out_dir / "selection.json").write_text(
        json.dumps(asdict(selection), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "README.md").write_text(
        render_readme(data, selection, tables, friedman, pairwise, horizon),
        encoding="utf-8",
        newline="\n",
    )
    return selection


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write the Engine 1 evaluation report.")
    parser.add_argument("--config", default="full")
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args(argv)
    selection = build_report(args.run_dir or DEFAULT_OUT_ROOT / args.config, args.out)
    print(f"served: {selection.served} ({selection.branch})")  # noqa: T201


if __name__ == "__main__":
    main()
