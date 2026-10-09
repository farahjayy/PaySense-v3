"""Engine 2 report: `python -m ml.engine2_train.report --config small|full` (plan P5, task D8).

Everything under `reports/engine2/` is written by this script from the stored run
(`data/engine2/runs/<config>/`) and the label manifest next to the labels file; nothing is edited
by hand. Benchmarks are in every table, and results are reported even when they are unflattering.
Every number in the prose is computed here from the run and the labels; a claim the run does not
support is not made (what was not run is listed under "Not done").
"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ml.engine2_train.data import LABELS_PATH, LOW_BASELINE, Dataset, load_labels  # noqa: E402
from ml.engine2_train.labels import MANIFEST_FILE  # noqa: E402
from ml.engine2_train.labelstats import (  # noqa: E402
    STOP_RULE_MARGIN,
    STOP_RULE_SHARE,
    baseline_facts,
)
from ml.engine2_train.models import CANDIDATES  # noqa: E402
from ml.engine2_train.provenance import sha256_file  # noqa: E402
from ml.engine2_train.train import RUNS_DIR  # noqa: E402

REPORT_DIR = Path(__file__).resolve().parents[3] / "reports" / "engine2"
DECIMALS = 4
FIGURE_DPI = 110
PNG_METADATA = {"Software": None}
BANDS = (0.10, 0.30)  # pre-registered: Safe < 0.10, Caution < 0.30, At Risk >= 0.30
PRICE_RATIO_EDGES = (0.0, 0.25, 0.5, 1.0, 2.0, np.inf)

NOT_DONE = """\
## Not done

- **Bias-term sensitivity.** The plan asked how the labels change if the served forecaster's level
  bias is removed from the simulation. That needs a second label run with the error record
  re-centred, which was not built; no claim about it is made.
- **Stale and incomplete ledgers in the training set.** The plan proposed adding them to training;
  the execution plan kept them apart, and they are kept apart (they are only used in the stress
  test, where training on them would contaminate it).
- **Repayment history** is not a feature (D-11) and is not modelled here.
"""


def _md(frame: pd.DataFrame) -> str:
    frame = frame.round(DECIMALS).fillna("")
    head = (
        "| " + " | ".join(map(str, frame.columns)) + " |\n"
        "|" + "|".join("---" for _ in frame.columns) + "|\n"
    )
    return head + "".join("| " + " | ".join(str(v) for v in r) + " |\n" for r in frame.to_numpy())


def _write(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.round(DECIMALS).to_csv(path, index=False, lineterminator="\n")


def _save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=FIGURE_DPI, metadata=PNG_METADATA, bbox_inches="tight")
    plt.close(fig)


def band_shares(labels: np.ndarray) -> dict[str, float]:
    return {
        "Safe": float((labels < BANDS[0]).mean()),
        "Caution": float(((labels >= BANDS[0]) & (labels < BANDS[1])).mean()),
        "At Risk": float((labels >= BANDS[1]).mean()),
    }


# ------------------------------------------------------------------ the label distribution
def _baseline_table(facts: dict[str, float | None]) -> pd.DataFrame:
    return pd.DataFrame([{"measure": k, "value": v} for k, v in facts.items()])


def _p_without_quantiles(base: np.ndarray) -> str:
    qs = np.quantile(base, [0.1, 0.25, 0.5, 0.75, 0.9])
    levels = (0.1, 0.25, 0.5, 0.75, 0.9)
    return ", ".join(f"P{int(q * 100)} {v:.3f}" for q, v in zip(levels, qs, strict=True))


def analysis_frame(path: Path) -> pd.DataFrame:
    """Label, baseline and the generator's persona / price ratio, for DESCRIBING the labels only.
    This reads the answer keys under `truth`; training and stress code never do."""
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            r = json.loads(line)
            if not r["locked"]:
                rows.append(
                    {
                        "persona": r["truth"]["persona"],
                        "price_to_income": r["truth"].get("price_to_income", np.nan),
                        "label": r["label"],
                        "p_without": r.get("p_without", np.nan),
                    }
                )
    return pd.DataFrame(rows)


def label_by_persona(frame: pd.DataFrame) -> pd.DataFrame:
    def stats(g: pd.DataFrame) -> pd.Series:
        return pd.Series(
            {
                "profiles": len(g),
                "mean_label": g["label"].mean(),
                "mean_p_without": g["p_without"].mean(),
                "share_safe": (g["label"] < BANDS[0]).mean(),
                "share_caution": ((g["label"] >= BANDS[0]) & (g["label"] < BANDS[1])).mean(),
                "share_at_risk": (g["label"] >= BANDS[1]).mean(),
            }
        )

    return frame.groupby("persona").apply(stats, include_groups=False).reset_index()


def label_by_price_ratio(frame: pd.DataFrame) -> pd.DataFrame:
    bins = pd.cut(frame["price_to_income"], list(PRICE_RATIO_EDGES), right=False)
    out = frame.groupby(bins, observed=True)["label"].agg(["count", "mean"]).reset_index()
    out["price_to_income"] = out["price_to_income"].astype(str)
    return out.rename(columns={"count": "profiles", "mean": "mean_label"})


# ------------------------------------------------------------------ tables from the run
def cv_table(record: dict[str, Any]) -> pd.DataFrame:
    sub = f"brier@{LOW_BASELINE}"
    rows = []
    for name in CANDIDATES:
        m = record["models"][name]
        rows.append(
            {
                "model": name,
                "brier": m["brier_mean"],
                "brier_se": m["brier_se"],
                f"brier_{LOW_BASELINE}": m.get(f"{sub}_mean"),
                "log_loss": m["log_loss_mean"],
                "auc_at_030": m["auc_at_030_mean"],
                "calibration_slope": m["calibration_slope_mean"],
                "ece": m["ece_mean"],
                "versus_winner_delta": record["versus_winner"].get(name, {}).get("delta"),
                "versus_winner_p_unadjusted": record["versus_winner"].get(name, {}).get("p"),
            }
        )
    rows.append({"model": "constant (the mean label)", "brier": record["constant_baseline_brier"]})
    return pd.DataFrame(rows)


def ablation_table(record: dict[str, Any]) -> pd.DataFrame:
    a = record["ablation"]
    rows = [{"subset": "all development profiles", **_ablation_row(a)}]
    for group, row in a.get("subgroups", {}).items():
        rows.append(
            {"subset": f"{group} (P(shortfall) without the purchase < 0.10)", **_ablation_row(row)}
        )
    return pd.DataFrame(rows)


def _ablation_row(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "brier_with_engine1": a["brier_with_engine1"],
        "brier_without_engine1": a["brier_without_engine1"],
        "delta_brier": a["delta_brier"],
        "delta_ci_low": a["delta_ci"][0],
        "delta_ci_high": a["delta_ci"][1],
        "t": a["t"],
        "p": a["p"],
    }


def lockbox_table(record: dict[str, Any]) -> pd.DataFrame:
    box = record["lockbox"]
    groups = box.get("subgroups", {}).get(LOW_BASELINE, {})
    return pd.DataFrame(
        [
            {
                "model": f"{record['winner']} (calibrated: {record['calibration']['chosen']})",
                "brier_all": box["calibrated"]["brier"],
                f"brier_{LOW_BASELINE}": groups.get("brier_calibrated"),
            },
            {
                "model": f"{record['winner']} (uncalibrated)",
                "brier_all": box["raw"]["brier"],
                f"brier_{LOW_BASELINE}": groups.get("brier_raw"),
            },
            {
                "model": "logistic (benchmark)",
                "brier_all": box["logistic_benchmark_brier"],
                f"brier_{LOW_BASELINE}": groups.get("brier_benchmark"),
            },
            {
                "model": "constant (development mean label; the subgroup's own mean there)",
                "brier_all": box["constant_brier"],
                f"brier_{LOW_BASELINE}": groups.get("brier_constant"),
            },
        ]
    )


def lockbox_subgroup_table(record: dict[str, Any]) -> pd.DataFrame:
    """The subgroup in full: Brier of each model, its own constant, and the calibration, ranking
    and band-agreement measures for the raw and the calibrated model."""
    rows = []
    for group, g in record["lockbox"].get("subgroups", {}).items():
        for kind, key in (("calibrated", "calibrated"), ("uncalibrated", "raw")):
            m = g[key]
            rows.append(
                {
                    "subgroup": group,
                    "model": f"{record['winner']} ({kind})",
                    "profiles": g["profiles"],
                    "brier": m["brier"],
                    "ece": m["ece"],
                    "calibration_slope": m["calibration_slope"],
                    "auc_at_030": m["auc_at_030"],
                    "band_agreement": g["band_agreement"] if kind == "calibrated" else None,
                }
            )
        rows.append(
            {"subgroup": group, "model": "logistic (benchmark)", "profiles": g["profiles"],
             "brier": g["brier_benchmark"]}
        )  # fmt: skip
        rows.append(
            {
                "subgroup": group,
                "model": f"constant ({g['constant_value']:.4f}, the subgroup's development mean)",
                "profiles": g["profiles"],
                "brier": g["brier_constant"],
            }
        )
    return pd.DataFrame(rows)


CLASS_LABELS = {
    "label_exactly_0": "label exactly 0",
    "label_between_0_and_1": "label strictly between 0 and 1",
    "label_exactly_1": "label exactly 1",
    "p_without_between_0_and_1": "baseline strictly between 0 and 1 (0 < p_without < 1)",
    "p_without_exactly_0_or_1": "baseline exactly 0 or exactly 1",
}


def lockbox_class_table(record: dict[str, Any]) -> pd.DataFrame:
    """Descriptive Brier by label class and by baseline class, lockbox only."""
    rows = []
    for key, row in record["lockbox"].get("brier_by_class", {}).items():
        rows.append(
            {
                "lockbox profiles": CLASS_LABELS.get(key, key),
                "profiles": row["profiles"],
                "share_of_lockbox": row["share_of_lockbox"],
                "brier_calibrated": row["brier_calibrated"],
                "brier_uncalibrated": row["brier_raw"],
                "brier_logistic": row["brier_benchmark"],
                "brier_constant": row["brier_constant"],
                "share_of_squared_error": row["share_of_squared_error"],
            }
        )
    return pd.DataFrame(rows)


def logistic_signs_table(record: dict[str, Any]) -> pd.DataFrame:
    rows = record["logistic_signs"]["features"]
    return pd.DataFrame(
        [
            {
                "feature": r["feature"],
                "coefficient_standardised": r["coefficient"],
                "monotone_direction": r["direction"],
                "agrees": "" if r["agrees"] is None else ("yes" if r["agrees"] else "NO"),
            }
            for r in rows
        ]
    )


def _signs_text(record: dict[str, Any]) -> str:
    signs = record["logistic_signs"]
    if record["served_model_has_monotone_constraints"]:
        served = f"Here the winner is {record['winner']}, so its monotone constraints apply."
    else:
        served = (
            "Here the logistic regression won, so the served model has no monotone constraints "
            "and the sign check below is the only evidence that its coefficients point the way "
            "the constraints would force."
        )
    return (
        "**Logistic coefficients against the monotone directions.** Of "
        f"{signs['constrained_features']} features with a known direction of effect, "
        f"{signs['agree']} have a standardised logistic coefficient with that sign and "
        f"{signs['disagree']} do not. If the logistic regression wins, the served model has no "
        f"monotone constraints. {served} The logistic benchmark itself is never constrained.\n"
    )


def _scoring_sentence(record: dict[str, Any]) -> str:
    n = record.get("lockbox_scorings")
    if n is None:
        return "The number of times the lockbox has been scored was not recorded."
    times = "time" if n == 1 else "times"
    return (
        "According to the append-only log beside the run directories, the lockbox has been "
        f"scored {n} {times} (counted from the log's first line; a scoring made before the log "
        "existed would not be in it)."
    )


def _lockbox_text(record: dict[str, Any]) -> str:
    box = record["lockbox"]
    c = box["calibrated"]
    return (
        f"The {box['profiles']} lockbox profiles (every tenth) were excluded from "
        "cross-validation, model choice, tuning, calibration and the ablation; the final "
        "calibrated model was scored "
        f"on them once. Brier {c['brier']:.4f}, log-loss {c['log_loss']:.4f}, calibration slope "
        f"{c['calibration_slope']:.3f}, ECE {c['ece']:.4f}; the model puts "
        f"{box['band_agreement']:.1%} of them in the same pre-registered band as the label. "
        f"{_scoring_sentence(record)}\n"
    )


def _subgroup_text(record: dict[str, Any]) -> str:
    classes = record["lockbox"].get("brier_by_class", {})
    zero = classes.get("label_exactly_0", {}).get("share_of_lockbox")
    one = classes.get("label_exactly_1", {}).get("share_of_lockbox")
    trivial = ""
    if zero is not None and one is not None:
        trivial = f"On the lockbox {zero:.1%} of labels are exactly 0 and {one:.1%} exactly 1. "
    return (
        "**Where the plan decides the band.** The subgroup whose baseline (no purchase) is under "
        "0.10 is scored in full below, beside its own constant benchmark (the subgroup's "
        "development mean label, not the overall one). Its labels are dominated by profiles "
        "whose label is exactly 0, which any model gets nearly right, so its Brier, ECE, "
        "calibration slope and band agreement look better than the subgroup deserves; the "
        "breakdown by label class shows how much of every score is those trivial profiles. "
        f"{trivial}The breakdown is descriptive: nothing was chosen or tuned on it.\n"
    )


def _sensitivity_text(record: dict[str, Any]) -> str:
    s = record["sensitivity"]
    mono, short = s["monotonicity"], s["shortfall_definition"]
    parts = ["## Sensitivity runs\n"]
    if mono["applicable"]:
        parts.append(
            f"**Monotone constraints.** The winner without constraints (tuned the same way, same "
            f"folds) has Brier {mono['brier_unconstrained']:.4f} against "
            f"{mono['brier_constrained']:.4f} with them; difference (free minus constrained) "
            f"{mono['delta_brier']:+.4f}, 95% CI {mono['delta_ci'][0]:+.4f} to "
            f"{mono['delta_ci'][1]:+.4f}, corrected p = {mono['p']:.3g}. "
            "A negative difference is the price paid for explainability.\n"
        )
    else:
        parts.append(f"**Monotone constraints.** Not applicable: {mono['reason']}.\n")
    curve = pd.DataFrame(s["learning_curve"])
    first, last = s["learning_curve"][0], s["learning_curve"][-1]
    parts.append(
        "**Learning curve** (ASSUMED 3: are about 10,000 profiles enough?). Brier on fixed "
        f"test folds as the training part grows: {first['brier']:.4f} with "
        f"{first['train_profiles']:.0f} profiles to {last['brier']:.4f} with "
        f"{last['train_profiles']:.0f}. Hyperparameters are the final tuned values, so the "
        "curve shows the shape, not an unbiased level.\n"
    )
    parts.append(_md(curve))
    if short["available"]:
        parts.append(
            "**Shortfall definition** (ASSUMED 4). If 'short' meant any single month below "
            "RM0 instead of the running total, the mean label would be "
            f"{short['mean_label_monthly']:.3f} instead of {short['mean_label_cumulative']:.3f}, "
            f"and {short['band_agreement_of_labels']:.1%} of profiles would keep the same band. "
            "The model trained on the running-total label has Brier "
            f"{short['brier_vs_cumulative']:.4f} against it and "
            f"{short['brier_vs_monthly']:.4f} "
            "against the per-month label (out-of-fold, no retraining).\n"
        )
    return "\n".join(parts)


def _limitations(
    data: Dataset, facts: dict[str, float | None], record: dict[str, Any], manifest: dict[str, Any]
) -> str:
    base = data.p_without
    saturation = ""
    if base is not None:
        saturation = (
            f"Before any purchase, {facts['share_p_without_at_or_above_safe_edge']:.1%} of the "
            f"generated students already have a simulated shortfall chance of 0.10 or more and "
            f"{facts['share_p_without_exactly_1']:.1%} have exactly 1.0 (baseline distribution: "
            f"{_p_without_quantiles(base)}). The purchase moves the band for "
            f"{facts['share_purchase_moves_the_band']:.1%} of profiles and changes the label "
            f"by under 0.01 for {facts['share_purchase_changes_label_by_under_001']:.1%}. The "
            "headline Brier "
            "therefore mostly measures how well the model reproduces the baseline; the subgroup "
            "where the baseline is under 0.10 is where the plan decides the band. It is reported "
            "separately in the cross-validation table (Brier), the ablation (every row), and the "
            "lockbox (Brier, calibration, band agreement, reliability and a breakdown by label "
            "class). It is NOT reported separately in the stress tests, the learning curve, the "
            "monotonicity run, the per-month definition run or the calibration choice."
        )
    floor = facts["monte_carlo_noise_floor_brier"]
    floor = "unknown (no manifest)" if floor is None else f"{floor:.5f}"
    paths = manifest.get("paths", "an unknown number of")
    return f"""\
## Read this before trusting any number

- **Engine 2 distils Engine 1.** The label is Engine 1's simulated probability of a shortfall, so a
  good score here shows that a fast, explainable model can reproduce the slow simulation. It does
  **not** show that the simulation, or the model, predicts what real students experience. The
  ablation is the evidence that the forecast-derived features matter; it is not evidence about
  real outcomes.
- **The population is synthetic.** The students, their ledgers and their purchases come from the
  generator in `reports/datagen/`, with assumed parameters. {saturation}
- **The generator was changed after its labels were inspected, twice.** The first label run
  showed roughly half of the generated students in deficit before any purchase, and the assumed
  allowances were raised (the `why` of `income.allowance_median_sen` in `params.yaml` records it;
  the label file of that run was not kept, so no before-histogram can be reproduced here). A
  later audit, before the full training run, found that long plans were truncated at 52 weeks
  and that every profile shared one calendar day; the horizon now runs to the last instalment
  (D-36) and each profile has its own as-of day. These were design corrections made on the
  label distribution, not on any model score, but they are choices made after looking.
- **Probabilities are more extreme than a calibrated forecast.** Engine 1's bands are narrower than
  nominal on short histories (`reports/engine1/serving_check.md`), and the labels inherit that.
- **Monte Carlo noise.** Each label is estimated from {paths} paths, so even a perfect model has
  a Brier floor of about {floor} (mean of label x (1 - label) divided by the paths).
- **Soft labels, grouped splits.** Each profile is one row; the folds are stratified on
  {record.get("strata", "a number of")} quantile bins of the soft label (ten requested; labels
  tied at exactly 0 or 1 merge bins); hyperparameters are tuned inside each training fold only.
- **The model-choice rule is approximate.** 'Within one standard error' uses the naive standard
  error of the fold scores, and the p-values against the winner in the first table are unadjusted
  for the number of comparisons (only the Holm-adjusted comparisons feed the choice).
- **Stress tests re-run the whole pipeline** on perturbed ledgers of the lockbox profiles and score
  the final calibrated model against the new simulated label.
- **Bands were fixed before training** (Safe below 0.10, Caution below 0.30, At Risk from 0.30) and
  are not tuned on these results. The lockbox rule (every tenth profile) and the 0.10 subgroup
  threshold were fixed before the full run, after the first harness and a 3-fold logistic sanity
  check on version-2 development labels (CHANGELOG), not before every model had been looked at.
"""


# ------------------------------------------------------------------ figures
def _calibration_figure(record: dict[str, Any], oof: np.ndarray | None, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(4.8, 4.4))
    ax.plot([0, 1], [0, 1], color="#94a3b8", linestyle="--", label="perfect")
    bins = pd.DataFrame(record["lockbox"]["reliability"])
    ax.plot(
        bins["mean_prediction"], bins["mean_label"], marker="o", color="#1d4ed8",
        label="lockbox (calibrated)",
    )  # fmt: skip
    ax.set_xlabel("Predicted probability")
    ax.set_ylabel("Mean simulated label")
    ax.set_title("Reliability of the final model")
    ax.legend()
    _save(fig, path)


def _histograms(data: Dataset, path: Path) -> None:
    fig, axes = plt.subplots(1, 2 if data.p_without is not None else 1, figsize=(9, 3.4))
    axes = np.atleast_1d(axes)
    axes[0].hist(data.y, bins=30, color="#c2410c")
    for edge in BANDS:
        axes[0].axvline(edge, color="#64748b", linestyle="--")
    axes[0].set_xlabel("Simulated probability of a shortfall with the plan")
    axes[0].set_ylabel("Profiles")
    axes[0].set_title("The labels, with the band edges")
    if data.p_without is not None:
        axes[1].hist(data.p_without, bins=30, color="#0f766e")
        axes[1].axvline(BANDS[0], color="#64748b", linestyle="--")
        axes[1].set_xlabel("Simulated probability without the purchase")
        axes[1].set_title("The baseline before any purchase")
    _save(fig, path)


# ------------------------------------------------------------------ the report
def _check_labels(record: dict[str, Any], labels_path: Path, data: Dataset) -> dict[str, Any]:
    """The manifest that sits beside THIS labels file, checked against the stored run."""
    manifest_path = labels_path.parent / MANIFEST_FILE
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    )
    stored = record.get("labels_sha256")
    if stored and sha256_file(labels_path) != stored:
        raise ValueError(f"{labels_path} is not the file this run was trained on")
    if manifest and stored and manifest["file"]["sha256"] != stored:
        raise ValueError(f"{manifest_path} does not describe the labels this run used")
    if data.capped is not None and data.capped.any():
        raise ValueError(
            f"{int(data.capped.sum())} labels have a truncated horizon; labels from "
            "after D-36 must simulate to the last instalment of every plan"
        )
    return manifest


def _capped_statement(data: Dataset) -> str:
    if data.capped is None:
        return "Whether the horizon was truncated was not recorded in this label file.\n"
    return (
        f"The simulation horizon was truncated for {int(data.capped.sum())} of {len(data)} labels "
        "(the report refuses to run if any label is truncated; D-36).\n"
    )


def build_report(run_dir: Path, out_dir: Path, labels_path: Path = LABELS_PATH) -> None:
    record = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    data = load_labels(labels_path)
    manifest = _check_labels(record, labels_path, data)
    stress_path = run_dir / "stress.json"
    stress = json.loads(stress_path.read_text(encoding="utf-8")) if stress_path.exists() else None
    paths = manifest.get("paths")
    facts = baseline_facts(data, paths)
    tables = out_dir / "tables"

    cv = cv_table(record)
    _write(cv, tables / "cv_metrics.csv")
    shares = band_shares(data.y)
    _write(
        pd.DataFrame([{"band": k, "share_of_labels": v} for k, v in shares.items()]),
        tables / "label_bands.csv",
    )
    _write(_baseline_table(facts), tables / "label_baseline.csv")
    ablation = ablation_table(record)
    _write(ablation, tables / "ablation.csv")
    calibration = pd.DataFrame(
        [
            {"option": k, "held_out_brier": v}
            for k, v in record["calibration"]["held_out_brier"].items()
        ]
    )
    _write(calibration, tables / "calibration.csv")
    lockbox = lockbox_table(record)
    _write(lockbox, tables / "lockbox.csv")
    _write(pd.DataFrame(record["lockbox"]["reliability"]), tables / "lockbox_reliability.csv")
    subgroup, classes = lockbox_subgroup_table(record), lockbox_class_table(record)
    signs = logistic_signs_table(record)
    _write(subgroup, tables / "lockbox_subgroup.csv")
    _write(classes, tables / "lockbox_by_class.csv")
    _write(signs, tables / "logistic_signs.csv")
    _write(pd.DataFrame(record["sensitivity"]["learning_curve"]), tables / "learning_curve.csv")
    analysis = analysis_frame(labels_path)
    by_persona, by_price = label_by_persona(analysis), label_by_price_ratio(analysis)
    _write(by_persona, tables / "label_by_persona.csv")
    _write(by_price, tables / "label_by_price_ratio.csv")
    stress_table = _stress_table(stress)
    if stress_table is not None:
        _write(stress_table, tables / "stress.csv")

    _figures(cv, data, record, run_dir, out_dir)
    sections = _sections(
        record, data, facts, manifest, shares,
        {"cv": cv, "ablation": ablation, "calibration": calibration, "lockbox": lockbox,
         "subgroup": subgroup, "classes": classes, "signs": signs, "persona": by_persona,
         "price": by_price, "stress": stress_table},
    )  # fmt: skip
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "README.md").write_text("\n".join(sections), encoding="utf-8", newline="\n")


def _stress_table(stress: dict[str, Any] | None) -> pd.DataFrame | None:
    if not stress:
        return None
    rows = [{"variant": "stored labels (lockbox)", **stress["stored_labels"]}]
    shifts = stress.get("mean_abs_label_shift_vs_identity", {})
    for name, row in stress["variants"].items():
        rows.append({"variant": name, **row, "mean_abs_label_shift_vs_identity": shifts.get(name)})
    return pd.DataFrame(rows)


def _figures(cv: pd.DataFrame, data: Dataset, record: dict, run_dir: Path, out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    ax.barh(cv["model"], cv["brier"], xerr=cv["brier_se"].fillna(0), color="#1d4ed8")
    ax.set_xlabel("Brier score against the soft label (lower is better)")
    ax.set_title("Cross-validated error by model (development profiles)")
    _save(fig, out_dir / "figures" / "brier_by_model.png")
    _histograms(data, out_dir / "figures" / "label_distribution.png")
    oof_path = run_dir / "oof_winner.npy"
    oof = np.load(oof_path) if oof_path.exists() else None
    _calibration_figure(record, oof, out_dir / "figures" / "reliability.png")


def _headline(record: dict[str, Any]) -> str:
    a, box = record["ablation"], record["lockbox"]
    low = a.get("subgroups", {}).get(LOW_BASELINE)
    text = (
        f"**Winner: `{record['winner']}`** ({record['reason']}); calibration: "
        f"`{record['calibration']['chosen']}`. Cross-validated Brier "
        f"{record['models'][record['winner']]['brier_mean']:.4f} against "
        f"{record['constant_baseline_brier']:.4f} for always predicting the mean label; on the "
        f"untouched lockbox {box['calibrated']['brier']:.4f} against {box['constant_brier']:.4f}. "
        f"Removing the {len(a['removed_features'])} Engine 1 features changes the "
        "cross-validated Brier by "
        f"{a['delta_brier']:+.4f} (95% CI {a['delta_ci'][0]:+.4f} to {a['delta_ci'][1]:+.4f}, "
        f"corrected p = {a['p']:.3g}): "
        + (
            "the forecast adds measurable skill."
            if a["delta_ci"][0] > 0
            else "the forecast-derived features do NOT add measurable skill on this data."
        )
    )
    if low:
        text += (
            f" Where the plan decides the band (baseline under 0.10) the change is "
            f"{low['delta_brier']:+.4f} (95% CI {low['delta_ci'][0]:+.4f} to "
            f"{low['delta_ci'][1]:+.4f})."
        )
    return text


def _sections(
    record: dict, data: Dataset, facts: dict, manifest: dict, shares: dict, tables: dict
) -> list[str]:
    config = record["config"]
    name = config["name"]
    return [
        "# Engine 2 training: BNPL risk classification\n",
        "> Generated by `python -m ml.engine2_train.report` - do not edit by hand.\n",
        f"Run `{name}`: {record['profiles']} labelled profiles "
        f"({record['development_profiles']} development, {record['lockbox_profiles']} lockbox), "
        f"{config['repeats']}x{config['folds']} grouped stratified CV, {config['trials']} Optuna "
        f"trials per model per fold, seed {config['seed']}, feature schema "
        f"`{record['feature_schema_hash']}`, commit `{record.get('git_commit')}`, labels sha256 "
        f"`{str(record.get('labels_sha256'))[:16]}`.\n",
        f"## Decision\n\n{_headline(record)}\n",
        _md(tables["cv"]),
        "Standard errors are naive (fold scores treated as independent); "
        "`versus_winner_p_unadjusted` is the corrected resampled t-test against the winner, "
        "not adjusted for the number of comparisons.\n",
        "![Brier](figures/brier_by_model.png)\n",
        "## The final model on the lockbox\n",
        _lockbox_text(record),
        _md(tables["lockbox"]),
        _subgroup_text(record),
        _md(tables["subgroup"]),
        "**Brier by label class** (lockbox, descriptive).\n",
        _md(tables["classes"]),
        "![Reliability](figures/reliability.png)\n",
        "## The labels\n",
        "Share of profiles in each pre-registered band: "
        + ", ".join(f"{k} {v:.1%}" for k, v in shares.items())
        + ". Share with a label of exactly 0: "
        f"{facts['share_label_exactly_0']:.1%}; exactly 1: {facts['share_label_exactly_1']:.1%}. "
        f"Stop rule (execution doc D4, more than {STOP_RULE_SHARE:.0%} within "
        f"{STOP_RULE_MARGIN} of 0 or 1): {facts['share_label_within_stop_margin']:.1%}, "
        + (
            "STOP."
            if facts["share_label_within_stop_margin"] > STOP_RULE_SHARE
            else "not triggered."
        )
        + "\n",
        _capped_statement(data),
        "![Labels](figures/label_distribution.png)\n",
        "### By persona and by purchase size\n",
        _md(tables["persona"]),
        _md(tables["price"]),
        "## Calibration\n\n"
        f"Chosen by cross-validation on the {record['calibration']['fitted_on']}, then fitted on "
        "all of them and stored with the model. The calibrator is fitted on out-of-fold "
        "predictions of the fold models but applied to a different model: "
        f"{record['calibration']['applied_to']}. Its correction is therefore approximate for the "
        "served model, which the lockbox reliability table checks. Explanations (SHAP, phase P6) "
        "will be computed on the raw scores of the model, while the number a student sees is the "
        "calibrated one, so a factor's contribution is on the raw scale.\n",
        _md(tables["calibration"]),
        "## Ablation: the contribution of the Engine 1 features\n",
        f"{record['ablation']['tuning']}; interval: {record['ablation']['ci_method']}.\n",
        _md(tables["ablation"]),
        _sensitivity_text(record),
        _signs_text(record),
        _md(tables["signs"]),
        "## Stress tests (lockbox profiles)\n",
        _md(tables["stress"]) if tables["stress"] is not None else "Not run.\n",
        _limitations(data, facts, record, manifest),
        NOT_DONE,
        f"\nLabel run: seed {manifest.get('seed')}, label version {manifest.get('label_version')}, "
        f"{manifest.get('profiles')} profiles, {manifest.get('locked_profiles')} locked, "
        f"{manifest.get('capped_profiles')} with a truncated horizon, "
        f"{manifest.get('paths')} paths, "
        f"parameter hash `{manifest.get('params_hash')}`, labels made at commit "
        f"`{manifest.get('git_commit')}`.\n",
        f"Libraries: {json.dumps(record.get('versions', {}), sort_keys=True)}.\n",
        "## Regenerate\n\n```\ncd backend\nuv run python -m ml.engine2_train.labels\n"
        f"uv run python -m ml.engine2_train.train --config {name}\n"
        f"uv run python -m ml.engine2_train.stress --config {name}\n"
        f"uv run python -m ml.engine2_train.report --config {name}\n```\n",
    ]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write the Engine 2 report.")
    parser.add_argument("--config", default="full")
    parser.add_argument("--labels", type=Path, default=LABELS_PATH)
    parser.add_argument("--out", type=Path, default=REPORT_DIR)
    args = parser.parse_args(argv)
    build_report(RUNS_DIR / args.config, args.out, args.labels)
    print(f"wrote {args.out}")  # noqa: T201


if __name__ == "__main__":
    main()
