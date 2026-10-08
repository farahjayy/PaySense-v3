"""Engine 1 report: `python -m ml.engine1_eval.report --config small|full` (plan P3, task B12).

Reads the stored results of a run and writes `reports/engine1/` (tables, figures, README,
`selection.json`). The model to serve is chosen mechanically by the rule fixed in the execution
doc before any result existed (ADR D-06); nothing here can change the rule after seeing numbers.
Benchmarks are in every table, and results are reported even when they are unflattering.
"""

import argparse
import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ml.engine1_eval.report_text import (  # noqa: E402
    ALL_SOURCES,
    CAVEATS,
    MATERIAL_MASE_DIFFERENCE,
    SIGNIFICANCE,
    md_table,
    rule_text,
)
from ml.engine1_eval.run import DEFAULT_OUT_ROOT  # noqa: E402
from ml.engine1_eval.stats import (  # noqa: E402
    bootstrap_median_ci,
    dm_hln,
    friedman_nemenyi,
    holm_adjust,
    wilcoxon_paired,
)

DEFAULT_REPORT_DIR = Path(__file__).resolve().parents[3] / "reports" / "engine1"
BENCHMARKS = ("naive", "ma4", "ma13")
LITERATURE = ("arima", "prophet", "lstm")
DECIMALS = 4
FIGURE_DPI = 110
PNG_METADATA = {"Software": None}
MIN_ORIGINS_FOR_DM = 3


@dataclass(frozen=True)
class Selection:
    best_literature: str
    best_benchmark: str
    served: str
    branch: str  # "literature" | "benchmark"
    p_value: float  # Holm-adjusted over the literature candidates vs the best benchmark
    median_difference: float  # best literature minus best benchmark; positive = literature worse
    ci_low: float
    ci_high: float
    n_series: int
    dropped_series: int  # series some model failed on, removed for every model
    metric: dict[str, float]


def select_model(scores: pd.DataFrame, seed: int = 0) -> Selection:
    """Apply the D-06 rule to per-series mean MASE (columns source, series_id, kind, model, mase).

    Only series that every model scored are used, so no model is flattered by failing on hard
    ones. Metric per model: mean over sources of the mean over that source's series, so one big
    source cannot drown a small real one. Serve the best literature candidate unless the best
    benchmark beats it by at least MATERIAL_MASE_DIFFERENCE with a Holm-adjusted Wilcoxon
    p < SIGNIFICANCE (Holm over every literature candidate against that benchmark).
    """
    wide = scores.pivot_table(index=["source", "series_id", "kind"], columns="model", values="mase")
    total = len(wide)
    complete = wide.dropna()
    if complete.empty:
        raise ValueError("no series was scored by every model")
    long = complete.reset_index().melt(
        id_vars=["source", "series_id", "kind"], var_name="model", value_name="mase"
    )
    per_source = long.groupby(["model", "source"])["mase"].mean().reset_index()
    metric = per_source.groupby("model")["mase"].mean().to_dict()
    literature = [m for m in metric if m in LITERATURE]
    benchmarks = [m for m in metric if m in BENCHMARKS]
    if not literature:
        raise ValueError("no literature candidate (arima, prophet, lstm) in the results")
    if not benchmarks:
        raise ValueError("no benchmark (naive, ma4, ma13) in the results")
    best_l = min(literature, key=lambda m: metric[m])
    best_b = min(benchmarks, key=lambda m: metric[m])

    tests = {
        m: wilcoxon_paired(complete[m].to_numpy(), complete[best_b].to_numpy()) for m in literature
    }
    adjusted = dict(zip(tests, holm_adjust([t.p_value for t in tests.values()]), strict=True))
    result = tests[best_l]
    low, high = bootstrap_median_ci(complete[best_l].to_numpy() - complete[best_b].to_numpy(), seed)
    benchmark_wins = (
        result.median_difference >= MATERIAL_MASE_DIFFERENCE and adjusted[best_l] < SIGNIFICANCE
    )
    return Selection(
        best_literature=best_l,
        best_benchmark=best_b,
        served=best_b if benchmark_wins else best_l,
        branch="benchmark" if benchmark_wins else "literature",
        p_value=adjusted[best_l],
        median_difference=result.median_difference,
        ci_low=low,
        ci_high=high,
        n_series=len(complete),
        dropped_series=total - len(complete),
        metric={m: float(v) for m, v in metric.items()},
    )


def _load(run_dir: Path) -> dict:
    def read(name: str) -> pd.DataFrame:
        return pd.read_csv(run_dir / name, dtype={"history_limit": "string"}, keep_default_na=True)

    frames = {name: read(f"{name}.csv") for name in ("results", "margin", "timing", "failures")}
    for name in ("results", "margin", "timing"):
        frames[name]["history_limit"] = frames[name]["history_limit"].fillna("")
    frames["run"] = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    return frames


def _numeric_limit(frame: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(frame["history_limit"], errors="coerce")


def _decision_rows(frame: pd.DataFrame, limit: float | None = None) -> pd.DataFrame:
    """Real-data rows plus the synthetic rows at one history limit (default: the longest)."""
    numeric = _numeric_limit(frame)
    chosen = numeric.max() if limit is None else limit
    return frame[frame["history_limit"].eq("") | numeric.eq(chosen)]


def _write(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.round(DECIMALS).to_csv(path, index=False, lineterminator="\n")


def _series_scores(results: pd.DataFrame, horizon: int, limit: float | None = None) -> pd.DataFrame:
    scores = (
        _decision_rows(results, limit)
        .groupby(["source", "series_id", "kind", "model"])[f"mase_{horizon}"]
        .mean()
        .reset_index()
        .rename(columns={f"mase_{horizon}": "mase"})
    )
    return scores.dropna()


def _tables(data: dict, horizon: int, out: Path) -> dict[str, pd.DataFrame]:
    results = data["results"]
    decision = _decision_rows(results)
    mase_cols = [c for c in results.columns if c.startswith("mase_")]
    margin_cols = [c for c in data["margin"].columns if c.startswith("margin_")]
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
    margin = (
        _decision_rows(data["margin"])
        .groupby(["source", "model"])[margin_cols]
        .mean()
        .reset_index()
    )
    bias = (
        decision.groupby(["source", "kind", "model"])[f"bias_{horizon}"]
        .mean()
        .reset_index()
        .rename(columns={f"bias_{horizon}": "mean_bias_mase_units"})
    )
    synthetic = results[results["source"] == "synthetic"]
    by_history = (
        synthetic.groupby(["history_limit", "model"])[f"mase_{horizon}"].mean().reset_index()
    )
    by_history["history_limit"] = pd.to_numeric(by_history["history_limit"]).astype(int)
    timing = data["timing"].copy()
    timing["ms_per_origin"] = timing["seconds"] / timing["origins"].clip(lower=1) * 1000
    tables = {
        "pooled_mase": pooled.sort_values(["source", "history_limit", "kind", "model"]),
        "coverage": coverage.sort_values(["source", "model"]),
        "margin": margin.sort_values(["source", "model"]),
        "bias": bias.sort_values(["source", "kind", "model"]),
        "by_history": by_history.sort_values(["history_limit", "model"]),
        "timing": timing.sort_values(["source", "history_limit", "model"]),
    }
    for name, frame in tables.items():
        _write(frame, out / "tables" / f"{name}.csv")
    return tables


def _friedman_table(scores: pd.DataFrame, out: Path) -> pd.DataFrame:
    rows = []
    for (source, kind), group in scores.groupby(["source", "kind"]):
        wide = group.pivot_table(index="series_id", columns="model", values="mase").dropna()
        if wide.shape[1] < 3 or wide.shape[0] < 5:
            continue
        result = friedman_nemenyi(wide.to_numpy().T, list(wide.columns))
        ranks = "; ".join(f"{m}={r:.2f}" for m, r in sorted(result.mean_ranks.items()))
        rows.append(
            {
                "source": source,
                "kind": kind,
                "series": wide.shape[0],
                "friedman_p": result.p_value,
                "critical_difference": result.critical_difference,
                "mean_ranks": ranks,
                "significant_pairs": "; ".join(f"{a}<>{b}" for a, b in result.significant_pairs),
            }
        )
    columns = ["source", "kind", "series", "friedman_p", "critical_difference", "mean_ranks"]
    frame = pd.DataFrame(rows, columns=[*columns, "significant_pairs"])
    _write(frame, out / "tables" / "friedman.csv")
    return frame


def _pairwise_table(
    scores: pd.DataFrame, selection: Selection, seed: int, out: Path
) -> pd.DataFrame:
    wide = scores.pivot_table(index=["source", "series_id", "kind"], columns="model", values="mase")
    wide = wide.dropna()
    rows = []
    for model in wide.columns:
        if model == selection.best_benchmark:
            continue
        a, b = wide[model].to_numpy(), wide[selection.best_benchmark].to_numpy()
        test = wilcoxon_paired(a, b)
        low, high = bootstrap_median_ci(a - b, seed)
        rows.append(
            {
                "model": model,
                "against": selection.best_benchmark,
                "series": len(wide),
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


def _stride(config: dict, source: str) -> int:
    if source == "synthetic":
        return int(config["stride"])
    return int(config[source]["stride"])


def _dm_table(data: dict, selection: Selection, horizon: int, out: Path) -> pd.DataFrame:
    """Per-series Diebold-Mariano (HLN) of the best literature model against the best benchmark,
    on the per-origin MASE at the longest horizon. Forecast windows overlap when the stride is
    shorter than the horizon, so consecutive origins' losses are treated as correlated."""
    config = data["run"]["config"]
    results = _decision_rows(data["results"])
    column = f"mase_{horizon}"
    rows = []
    for source, group in results.groupby("source"):
        overlap = max(1, math.ceil(horizon / _stride(config, source)))
        tested = significant = literature_better = 0
        statistics = []
        for _, series in group.groupby(["series_id", "kind"]):
            pivot = series.pivot_table(index="origin", columns="model", values=column)
            if selection.best_literature not in pivot or selection.best_benchmark not in pivot:
                continue
            pair = pivot[[selection.best_literature, selection.best_benchmark]].dropna()
            if len(pair) < MIN_ORIGINS_FOR_DM:
                continue
            outcome = dm_hln(
                pair[selection.best_literature].to_numpy(),
                pair[selection.best_benchmark].to_numpy(),
                overlap,
            )
            tested += 1
            statistics.append(outcome.statistic)
            significant += outcome.p_value < SIGNIFICANCE
            literature_better += outcome.p_value < SIGNIFICANCE and outcome.statistic < 0
        rows.append(
            {
                "source": source,
                "literature": selection.best_literature,
                "benchmark": selection.best_benchmark,
                "series_tested": tested,
                "share_literature_better": literature_better / tested if tested else float("nan"),
                "share_significant_either_way": significant / tested if tested else float("nan"),
                "overlapping_origins": overlap,
            }
        )
    frame = pd.DataFrame(rows)
    _write(frame, out / "tables" / "diebold_mariano.csv")
    return frame


def _by_history_selection(data: dict, horizon: int, seed: int, out: Path) -> pd.DataFrame:
    """The same rule applied at every history length shown to the models."""
    rows = []
    limits = sorted(_numeric_limit(data["results"]).dropna().unique())
    for limit in limits:
        try:
            s = select_model(_series_scores(data["results"], horizon, limit), seed)
        except ValueError:
            continue
        rows.append(
            {
                "history_weeks": int(limit),
                "best_literature": s.best_literature,
                "best_benchmark": s.best_benchmark,
                "served": s.served,
                "branch": s.branch,
                "median_difference": s.median_difference,
                "p_holm": s.p_value,
            }
        )
    frame = pd.DataFrame(rows)
    _write(frame, out / "tables" / "selection_by_history.csv")
    return frame


def _winners_by_source(scores: pd.DataFrame, out: Path) -> pd.DataFrame:
    means = scores.groupby(["source", "model"])["mase"].mean().reset_index()
    rows = []
    for source, group in means.groupby("source"):
        best = group.loc[group["mase"].idxmin()]
        literature = group[group["model"].isin(LITERATURE)]
        rows.append(
            {
                "source": source,
                "best_model": best["model"],
                "best_literature": literature.loc[literature["mase"].idxmin(), "model"]
                if len(literature)
                else "",
            }
        )
    frame = pd.DataFrame(rows)
    _write(frame, out / "tables" / "winners_by_dataset.csv")
    return frame


def _margin_sentence(tables: dict[str, pd.DataFrame], selection: Selection, horizon: int) -> str:
    margin = tables["margin"]
    column = f"margin_{horizon}"
    if column not in margin:
        return ""
    metric = margin.groupby("model")[column].mean().sort_values()
    rank = list(metric.index).index(selection.served) + 1 if selection.served in metric else 0
    sentence = (
        f"On {horizon}-week cumulative-margin error (mean over datasets) the served model "
        f"`{selection.served}` ranks {rank} of {len(metric)} "
        f"({metric.get(selection.served, float('nan')):.3f} against {metric.iloc[0]:.3f} for "
        f"`{metric.index[0]}`)."
    )
    if rank != 1:
        sentence += (
            " **The MASE winner is not the margin winner**: see the first caveat and the bias "
            "table. P4 must check the served model's level bias before Engine 2 relies on it."
        )
    return sentence


def _save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=FIGURE_DPI, metadata=PNG_METADATA, bbox_inches="tight")
    plt.close(fig)


def _figures(tables: dict[str, pd.DataFrame], horizon: int, out: Path) -> None:
    pooled = tables["pooled_mase"]
    numeric = pd.to_numeric(pooled["history_limit"], errors="coerce")
    decision = pooled[pooled["history_limit"].eq("") | numeric.eq(numeric.max())]
    wide = decision.groupby(["source", "model"])[f"mase_{horizon}"].mean().unstack("source")
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    wide.plot.bar(ax=ax)
    ax.axhline(1.0, color="#94a3b8", linewidth=1, linestyle="--")
    ax.set_ylabel(f"Mean MASE, {horizon}-week horizon")
    ax.set_title("Forecast error by model and dataset (1.0 = the naive error)")
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


def render_readme(parts: dict, selection: Selection, horizon: int) -> str:
    data = parts["data"]
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
        f"Holm-adjusted Wilcoxon p = {s.p_value:.4g} over {s.n_series} series "
        f"({s.dropped_series} dropped because some model failed on them)."
    )
    decision = pd.DataFrame(sorted(s.metric.items()), columns=["model", "decision_metric"])
    tables = parts["tables"]
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
        f"{availability} Model failures recorded: {len(data['failures'])} "
        "(`failures.csv` in the run directory).\n",
        f"## Decision\n\n{rule_text(horizon)}\n\n{headline}\n",
        md_table(decision),
        f"{_margin_sentence(tables, selection, horizon)}\n",
        "![MASE by model](figures/mase_by_model.png)\n",
        "### The same rule at each history length\n",
        md_table(parts["by_history_selection"]),
        "### Best model per dataset\n",
        md_table(parts["winners"]),
        "## Against the best benchmark\n",
        md_table(parts["pairwise"]) if len(parts["pairwise"]) else "Not enough paired series.\n",
        "### Diebold-Mariano (HLN), per series, best literature model vs best benchmark\n",
        md_table(parts["dm"]),
        "## Friedman and Nemenyi (lower rank is better)\n",
        md_table(parts["friedman"]) if len(parts["friedman"]) else "Not enough series.\n",
        "## Error by dataset, kind and model\n",
        md_table(tables["pooled_mase"]),
        "![MASE by history](figures/mase_by_history.png)\n",
        "## Bias (mean forecast minus actual, in naive-error units; above 0 = over-forecast)\n",
        md_table(tables["bias"]),
        "## Cumulative-margin error (scaled)\n",
        md_table(tables["margin"]),
        "## Interval coverage\n",
        md_table(tables["coverage"]),
        "![Coverage](figures/coverage.png)\n",
        "## Cost\n",
        md_table(tables["timing"]),
        CAVEATS,
        regenerate,
    ]
    return "\n".join(sections)


def build_report(run_dir: Path, out_dir: Path) -> Selection:
    data = _load(run_dir)
    horizon = int(data["run"]["config"]["horizon"])
    seed = int(data["run"]["config"]["seed"])
    tables = _tables(data, horizon, out_dir)
    scores = _series_scores(data["results"], horizon)
    selection = select_model(scores, seed)
    parts = {
        "data": data,
        "tables": tables,
        "friedman": _friedman_table(scores, out_dir),
        "pairwise": _pairwise_table(scores, selection, seed, out_dir),
        "dm": _dm_table(data, selection, horizon, out_dir),
        "by_history_selection": _by_history_selection(data, horizon, seed, out_dir),
        "winners": _winners_by_source(scores, out_dir),
    }
    _figures(tables, horizon, out_dir)
    (out_dir / "selection.json").write_text(
        json.dumps(asdict(selection), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "README.md").write_text(
        render_readme(parts, selection, horizon), encoding="utf-8", newline="\n"
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
