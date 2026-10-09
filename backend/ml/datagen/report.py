"""Distribution report for the synthetic population (plan P2, A12): `python -m ml.datagen.report`.

Everything under `reports/datagen/` is written by this script from a fresh generation; nothing
there is edited by hand (CLAUDE.md hard constraint 5). Generated moments sit beside their cited
targets, misses included, with the assumed parameters and the limitations stated up front.
"""

import argparse
import csv
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # no display needed, and the output is deterministic
import matplotlib.pyplot as plt  # noqa: E402

from ml.datagen.export import DEFAULT_SEED  # noqa: E402
from ml.datagen.params import Param, Params, load_params  # noqa: E402
from ml.datagen.profile import PERSONAS, generate_profile  # noqa: E402
from ml.datagen.report_stats import Collector, moments  # noqa: E402

DEFAULT_OUT_DIR = Path(__file__).resolve().parents[3] / "reports" / "datagen"
DEFAULT_PROFILES = 10_000  # the size of the exported population (MANIFEST.json)
BAND_LOW_RM, BAND_HIGH_RM = 201, 400  # the cited modal monthly spending band
FIGURE_DPI = 110
PERSONA_COLOURS = {
    "frequent_bnpl": "#c2410c",
    "budget_conscious": "#1d4ed8",
    "irregular_income": "#15803d",
}
PNG_METADATA = {"Software": None}  # keep figure bytes independent of the matplotlib build string

LIMITATIONS = """\
## Limitations

- **There are no real students here.** Every profile is synthetic, so every result trained or
  evaluated on it describes the generator as much as it describes the models.
- **The data is partly circular by construction.** The generator and the forecasters are written
  by the same author. To limit this, the weekly series carries structure the forecasters are not
  told about (AR(1) drift in the spending level, a payday-week lift, exam-week dips, occasional
  very large weeks; day-of-week effects only reshuffle spending inside a week and do not reach the
  weekly series), but a forecaster that happens to match those effects will look better than it
  would on real data. Real-data benchmarks (Berka, if obtainable) are used only as
  a sanity check, never as the headline result.
- **Most parameters are assumptions.** Published figures about Malaysian student finances are
  scarce, so the majority of parameters are assumed; the cited ones are listed with their source in
  `tables/parameters.csv`. Assumed values are chosen to be plausible and to span the range the
  models must handle, then stress-tested rather than defended.
- **The spending band is an interpretation.** The cited study reports that many students spend
  RM201-400 a month, most naturally their total spending. The generator applies it to
  *discretionary* spending only and adds rent, phone and subscriptions on top, so total
  spending is higher than the band. This is a modelling choice, not something the source says.
- **Provider rules are simplified.** SPayLater's 6-month plan (fee disputed in the billing-rules
  note) is left out, and the 3-month 0% plan, which applies to Shopee marketplace checkouts, is
  modelled as available on every SPayLater purchase.
- **Many "cited" rows are wiring checks.** Rows marked `cited (wiring check)` hold by construction
  (an instalment count drawn from the provider's own list is in that list). They show the cited
  rules were applied, not that the population matches reality. The distribution comparisons are the
  spend level, the category shares and the per-holder repayment shares.
- **Cited targets are checked, not proven.** A generated moment landing near its target shows the
  generator is wired correctly; it does not show the population is realistic. The cited repayment
  figures describe account holders (not instalments) and are compared per holder.
- **Reproducibility is verified on one software stack.** Regeneration is byte-identical on the
  machine and package versions recorded in `data/synthetic/MANIFEST.json`. A different numpy
  version or CPU could change a transaction by a sen (exp/log are CPU-dispatched), and a different
  matplotlib build changes figure bytes; the tables are the record, the figures are illustrations.
- **Labels are simulated.** Engine 2's label is Engine 1's simulated shortfall probability, so the
  risk model inherits whatever the forecaster and the simulation get wrong.
- **Two calendars.** This export and the Engine 1 cohort use the fixed as-of day 2025-12-28.
  Engine 2 labels draw each profile's as-of day uniformly over one year (`calendar.*` parameters),
  so the PTPTN position, the semester and the plan horizon differ between labels (ADR D-31 note).
"""


def parameter_rows(params: Params) -> list[dict[str, Any]]:
    def provenance(p: Param) -> str:
        return "assumed" if p.assumed else f"cited: {p.source}"

    return [
        {
            "path": p.path,
            "value": p.value,
            "unit": p.unit,
            "provenance": provenance(p),
            "why": p.why or "",
        }
        for p in params.all()
    ]


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _save(fig: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=FIGURE_DPI, metadata=PNG_METADATA, bbox_inches="tight")
    plt.close(fig)


def _fig_monthly_spend(c: Collector, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for persona in PERSONAS:
        values = [v / 100 for v in c.monthly_spend.get(persona, [])]
        if values:
            ax.hist(values, bins=40, alpha=0.55, color=PERSONA_COLOURS[persona], label=persona)
    ax.axvspan(BAND_LOW_RM, BAND_HIGH_RM, color="#94a3b8", alpha=0.25, label="cited modal band")
    ax.set_xlabel("Monthly discretionary spend (RM)")
    ax.set_ylabel("Student-months")
    ax.set_title("Monthly spending by persona against the cited RM201-400 band")
    ax.legend()
    _save(fig, path)


def _fig_repayment(c: Collector, path: Path) -> None:
    holders = c.holders_on_time + c.holders_late + c.holders_missed
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    labels = ["all on time", "paid late", "missed one"]
    generated = [
        x / holders if holders else 0 for x in (c.holders_on_time, c.holders_late, c.holders_missed)
    ]
    cited = [
        c.params["repayment.on_time_share"],
        c.params["repayment.late_but_paid_share"],
        c.params["repayment.missed_share"],
    ]
    xs = range(len(labels))
    ax.bar([x - 0.2 for x in xs], cited, width=0.4, color="#94a3b8", label="cited")
    ax.bar([x + 0.2 for x in xs], generated, width=0.4, color="#1d4ed8", label="generated")
    ax.set_xticks(list(xs), labels)
    ax.set_ylabel("Share of account holders")
    ax.set_title("Repayment behaviour, per holder")
    ax.legend()
    _save(fig, path)


def _fig_purchase_ratio(c: Collector, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.hist(c.ratios, bins=40, color="#c2410c")
    ax.set_xscale("log")
    ax.set_xlabel("Proposed price / monthly income (log scale)")
    ax.set_ylabel("Profiles")
    ax.set_title("Proposed purchases span trivial to unaffordable")
    _save(fig, path)


def _fig_weekly_examples(c: Collector, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    for persona in PERSONAS:
        series = c.examples.get(persona)
        if series:
            ax.plot(
                [i for i, _ in enumerate(series)],
                [w.discretionary_sen / 100 for w in series],
                color=PERSONA_COLOURS[persona],
                label=persona,
                linewidth=1.2,
            )
    ax.set_xlabel("Week of history")
    ax.set_ylabel("Weekly discretionary spend (RM)")
    ax.set_title("One example profile per persona")
    ax.legend()
    _save(fig, path)


def _md_table(rows: list[dict[str, Any]], columns: Sequence[str]) -> str:
    head = "| " + " | ".join(columns) + " |\n|" + "|".join("---" for _ in columns) + "|\n"
    body = "".join(
        "| " + " | ".join(str(r[c]).replace("|", "/") for c in columns) + " |\n" for r in rows
    )
    return head + body


def render_readme(params: Params, seed: int, count: int, rows: list[dict[str, Any]]) -> str:
    assumed = [
        {"parameter": f"`{p.path}`", "value": p.value, "why": p.why} for p in params.assumed()
    ]
    outside = [r for r in rows if r["status"] == "outside tolerance"]
    verdict = (
        "Every measured moment with a target is within its tolerance."
        if not outside
        else "Moments outside tolerance (reported, not tuned away): "
        + ", ".join(f"`{r['param']}`" for r in outside)
        + "."
    )
    return (
        "# Synthetic population: distribution report\n\n"
        "> Generated by `python -m ml.datagen.report` - do not edit by hand.\n\n"
        f"Run: seed {seed}, {count} profiles, parameter hash `{params.hash()}`.\n\n"
        f"{len(params.cited())} of {len(params.all())} parameters are cited; "
        f"{len(params.assumed())} are assumed.\n\n"
        f"{verdict}\n\n"
        "## Generated moments against their targets\n\n"
        + _md_table(rows, ["param", "kind", "target", "measured", "unit", "status", "note"])
        + "\n![Monthly spending](figures/monthly_spend.png)\n\n"
        "![Repayment](figures/repayment.png)\n\n"
        "![Proposed purchases](figures/purchase_ratio.png)\n\n"
        "![Example weekly series](figures/weekly_examples.png)\n\n"
        "## Assumed parameters\n\n"
        "None of these has a published source; each is a choice, and the reason is stated.\n\n"
        + _md_table(assumed, ["parameter", "value", "why"])
        + "\n"
        + LIMITATIONS
        + "\n## Regenerate\n\n"
        "```\ncd backend\nuv run python -m ml.datagen.report\n```\n"
    )


def build_report(params: Params, seed: int, count: int, out_dir: Path) -> None:
    if count < 1:
        raise ValueError("count must be at least 1")
    collector = Collector(params)
    for index in range(count):
        collector.add(generate_profile(params, seed, index))
    rows = moments(collector)

    _write_csv(
        out_dir / "tables" / "parameters.csv",
        parameter_rows(params),
        ["path", "value", "unit", "provenance", "why"],
    )
    _write_csv(
        out_dir / "tables" / "moments.csv",
        rows,
        ["param", "description", "unit", "kind", "target", "measured", "status", "note"],
    )
    figures = out_dir / "figures"
    _fig_monthly_spend(collector, figures / "monthly_spend.png")
    _fig_repayment(collector, figures / "repayment.png")
    _fig_purchase_ratio(collector, figures / "purchase_ratio.png")
    _fig_weekly_examples(collector, figures / "weekly_examples.png")
    (out_dir / "README.md").write_text(
        render_readme(params, seed, count, rows), encoding="utf-8", newline="\n"
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Regenerate the synthetic-population report.")
    parser.add_argument("--profiles", type=int, default=DEFAULT_PROFILES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    build_report(load_params(), args.seed, args.profiles, args.out)
    print(f"wrote report to {args.out}")  # noqa: T201 - CLI entry point


if __name__ == "__main__":
    main()
