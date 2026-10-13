"""The three UAT persona CSVs (plan P2, A10): `python -m ml.datagen.personas`.

Testers do not upload their own statements; each uploads a pre-made, persona-matched history of
at least four months (academic constraints, section 3). Every file is synthetic, built from a
fixed seed so the output is byte-for-byte reproducible, and chosen (deterministically) from the
first profile that actually shows what the persona exists to test.
"""

import csv
import io
from collections.abc import Callable
from pathlib import Path

from app.domain.categorize import BNPL, REFUND, TRANSFER
from ml.datagen.params import Params, load_params
from ml.datagen.profile import StudentProfile, generate_profile

PERSONA_SEEDS = {"frequent_bnpl": 1101, "budget_conscious": 1202, "irregular_income": 1303}
SEARCH_LIMIT = 1000  # candidate profiles tried per persona before giving up
MIN_SHOWCASE_ROWS = 3
# The supervisor asks for at least four months before the forecast unlocks (history.persona_months);
# the forecast also needs 17 complete Monday-Sunday weeks, and four calendar months can hold fewer
# (a file that starts on a Tuesday has 16). One extra month leaves room, including for the shift to
# a session date. Kept here, not in params.yaml, so the labels' provenance hash is unchanged.
PERSONA_EXTRA_MONTHS = 1
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "personas"
OUTFLOW_TYPES = ("expense", "savings")


def _count(profile: StudentProfile, category: str) -> int:
    return sum(1 for t in profile.transactions if t.category == category)


def _has_messy_rows(profile: StudentProfile) -> bool:
    return _count(profile, REFUND) > 0 and _count(profile, TRANSFER) > 0


def _net_sen(profile: StudentProfile) -> int:
    signed = (
        -t.amount_sen if t.type in OUTFLOW_TYPES else t.amount_sen for t in profile.transactions
    )
    return sum(signed)


SHOWCASE: dict[str, Callable[[StudentProfile], bool]] = {
    "frequent_bnpl": lambda p: _count(p, BNPL) >= MIN_SHOWCASE_ROWS,
    # solvent but tight: no BNPL, no gigs, and the whole history ends no worse than break-even
    "budget_conscious": lambda p: (
        _count(p, BNPL) == 0 and _count(p, "Gig") == 0 and _net_sen(p) >= 0
    ),
    "irregular_income": lambda p: _count(p, "Gig") >= MIN_SHOWCASE_ROWS,
}


def build_persona_profile(params: Params, persona: str) -> StudentProfile:
    """The first candidate profile that shows what this persona exists to test."""
    months = int(params["history.persona_months"]) + PERSONA_EXTRA_MONTHS
    for index in range(SEARCH_LIMIT):
        profile = generate_profile(
            params, PERSONA_SEEDS[persona], index, persona=persona, history_months=months
        )
        if SHOWCASE[persona](profile) and _has_messy_rows(profile):
            return profile
    raise RuntimeError(f"no {persona} profile in {SEARCH_LIMIT} candidates shows the persona")


def _ringgit(amount_sen: int, outflow: bool) -> str:
    sign = "-" if outflow else ""
    ringgit, sen = divmod(abs(amount_sen), 100)
    return f"{sign}{ringgit}.{sen:02d}"


def render_csv(profile: StudentProfile) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["Date", "Description", "Amount"])
    for t in profile.transactions:
        writer.writerow(
            [
                t.date.strftime("%d/%m/%Y"),
                t.description,
                _ringgit(t.amount_sen, t.type in OUTFLOW_TYPES),
            ]
        )
    return out.getvalue()


def write_personas(params: Params, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for persona in PERSONA_SEEDS:
        path = out_dir / f"{persona}.csv"
        path.write_bytes(render_csv(build_persona_profile(params, persona)).encode("utf-8"))
        written.append(path)
    return written


def main() -> None:
    for path in write_personas(load_params(), DEFAULT_OUT_DIR):
        print(f"wrote {path}")  # noqa: T201 - command-line entry point


if __name__ == "__main__":
    main()
