"""Analyse a UAT run:  uv run python -m ml.uat.analyse --data ../uat/data/<run> --out <report.md>

Reads sus.csv, clarity.csv and vignettes.csv from the data folder and the vignette options from
uat/vignettes.yaml. Prints the report and, with --out, writes it plus two CSV tables beside it.
"""

import argparse
import csv
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

from ml.uat.load import (
    CLARITY_ITEMS,
    UatDataError,
    load_choices,
    load_clarity,
    load_sus,
    load_vignettes,
)
from ml.uat.sus import mean_interval, sus_score
from ml.uat.switches import SwitchRow, switch_table

DEFAULT_VIGNETTES = Path(__file__).resolve().parents[3] / "uat" / "vignettes.yaml"
INVENTED_BANNER = (
    "> **Invented example data.** These answers were made up to test the script. They are not "
    "results and must not be quoted as findings."
)
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: object) -> str:
    """A CSV cell that a spreadsheet will not run as a formula."""
    text = str(value)
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            writer.writerow([safe_cell(cell) for cell in row])


def _fmt(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def sus_section(scores: dict[str, float]) -> list[str]:
    interval = mean_interval(list(scores.values()))
    ci = (
        "no interval (fewer than two testers)"
        if interval.low is None or interval.high is None
        else f"95% CI {interval.low:.1f} to {interval.high:.1f}"
    )
    lines = [
        "## System Usability Scale",
        "",
        f"Mean SUS **{interval.mean:.1f}** from {interval.n} "
        f"{'tester' if interval.n == 1 else 'testers'} ({ci}). "
        "A score of about 68 is the usual benchmark for average usability.",
        "",
        "| Tester | SUS |",
        "|---|---|",
    ]
    lines += [f"| {who} | {score:.1f} |" for who, score in sorted(scores.items())]
    return lines


def clarity_section(answers: dict[str, list[int]]) -> list[str]:
    lines = ["## Explanation clarity (1 = strongly disagree, 5 = strongly agree)", ""]
    lines += ["| Item | Mean | n |", "|---|---|---|"]
    for i in range(CLARITY_ITEMS):
        column = [a[i] for a in answers.values()]
        lines.append(f"| C{i + 1} | {_fmt(sum(column) / len(column), 2)} | {len(column)} |")
    return lines


def switch_section(rows: list[SwitchRow]) -> list[str]:
    lines = [
        "## Decisions before and after the risk check",
        "",
        "Counts only: with this few testers a significance test would overstate the evidence. "
        "Safer / riskier follows the risk ranking of the options in `uat/vignettes.yaml`.",
        "",
        "| Vignette | Testers | Same | Safer | Riskier | Confidence before | Confidence after |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.vignette}: {r.title} | {r.n} | {r.same} | {r.safer} | {r.riskier} | "
            f"{_fmt(r.confidence_before, 2)} | {_fmt(r.confidence_after, 2)} |"
        )
    for r in rows:
        moves = [f"{a} to {b}: {n}" for a, b, n in r.transitions if a != b]
        lines += ["", f"**{r.vignette}** changes: " + (", ".join(moves) if moves else "none")]
    return lines


def build_report(data: Path, vignettes_path: Path) -> tuple[str, dict[str, float], list[SwitchRow]]:
    vignettes = load_vignettes(vignettes_path)
    sus, sus_invented = load_sus(data / "sus.csv")
    clarity, clarity_invented = load_clarity(data / "clarity.csv")
    choices, choices_invented = load_choices(data / "vignettes.csv", vignettes)
    scores = {who: sus_score(a) for who, a in sus.items()}
    table = switch_table(choices, vignettes)

    lines = ["# UAT analysis", ""]
    if sus_invented or clarity_invented or choices_invented:
        lines += [INVENTED_BANNER, ""]
    lines += sus_section(scores) + [""] + clarity_section(clarity) + [""] + switch_section(table)
    return "\n".join(lines) + "\n", scores, table


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--vignettes", type=Path, default=DEFAULT_VIGNETTES)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        report, scores, table = build_report(args.data, args.vignettes)
    except (UatDataError, FileNotFoundError) as err:
        print(f"Cannot analyse: {err}", file=sys.stderr)
        return 2
    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        write_csv(
            args.out.with_name(f"{args.out.stem}_sus_scores.csv"),
            ["participant", "sus"],
            scores.items(),
        )
        write_csv(
            args.out.with_name(f"{args.out.stem}_switches.csv"),
            ["vignette", "n", "same", "safer", "riskier", "confidence_before", "confidence_after"],
            [
                (
                    r.vignette,
                    r.n,
                    r.same,
                    r.safer,
                    r.riskier,
                    r.confidence_before,
                    r.confidence_after,
                )
                for r in table
            ],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
