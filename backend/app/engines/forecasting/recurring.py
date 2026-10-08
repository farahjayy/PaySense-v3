"""Recurring-item detection (plan P4, task C1). Suggests; the user confirms.

Heuristic (PRD 3.1): normalise the merchant text, group by direction and text, require at least
three occurrences whose gaps sit in one cadence window (weekly, biweekly, monthly, semester;
a skipped period is tolerated) and whose amounts stay within 15% of the group's median. Nothing
here writes to the ledger: a suggestion becomes a recurring item only when the user confirms it.
"""

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Any

from app.domain.categorize import BNPL, REFUND, TRANSFER
from app.domain.flows import as_date

MIN_OCCURRENCES = 3
AMOUNT_TOLERANCE = 0.15
MIN_SHARE = 0.75  # share of gaps / amounts that must fit the pattern
SKIPPED_PERIODS = (1, 2)  # a gap of two periods means one occurrence was missed
# Gap windows in days: (low, high) for one period.
CADENCE_WINDOWS = {
    "weekly": (6, 8),
    "biweekly": (13, 16),
    "monthly": (26, 35),
    "semester": (150, 215),
}
EXCLUDED_CATEGORIES = {REFUND, TRANSFER, BNPL}
NON_LETTERS = re.compile(r"[^a-z ]+")
SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class Suggestion:
    name: str  # normalised merchant text: the grouping key
    display_name: str  # the latest original description, for showing to the user
    kind: str  # "income" | "bill"
    amount_sen: int  # median amount
    cadence: str
    anchor_date: date  # the latest occurrence
    confidence: float  # 0 to 1: how clean the pattern is
    occurrences: int


def normalise_merchant(text: str | None) -> str:
    """Lower-case letters only: digits, references, dates and punctuation are dropped."""
    if not text:
        return ""
    return SPACES.sub(" ", NON_LETTERS.sub(" ", text.lower())).strip()


def _candidate(row: Mapping[str, Any]) -> bool:
    if row.get("type") not in ("income", "expense"):
        return False  # savings are not recurring bills
    if row.get("category") in EXCLUDED_CATEGORIES:
        return False
    if row.get("bnpl_plan_id") or row.get("bnpl_installment_id") or row.get("recurring_item_id"):
        return False
    return int(row.get("amount_sen") or 0) > 0 and bool(normalise_merchant(row.get("description")))


def _gap_fits(gap: int, window: tuple[int, int]) -> bool:
    low, high = window
    return any(k * low <= gap <= k * high for k in SKIPPED_PERIODS)


def _cadence(gaps: list[int]) -> tuple[str, float] | None:
    """The cadence whose window holds the median gap, and the share of gaps that fit it."""
    middle = median(gaps)
    for cadence, window in CADENCE_WINDOWS.items():
        if window[0] <= middle <= window[1]:
            share = sum(_gap_fits(g, window) for g in gaps) / len(gaps)
            return (cadence, share) if share >= MIN_SHARE else None
    return None


def _amount_stats(amounts: list[int]) -> tuple[int, float, float] | None:
    """Median amount, share within tolerance of it, and the relative mean absolute deviation."""
    centre = median(amounts)
    within = [a for a in amounts if abs(a - centre) <= AMOUNT_TOLERANCE * centre]
    share = len(within) / len(amounts)
    if share < MIN_SHARE:
        return None
    spread = sum(abs(a - centre) for a in amounts) / len(amounts) / centre
    return int(round(centre)), share, spread


def detect(
    rows: Iterable[Mapping[str, Any]],
    confirmed: Iterable[tuple[str, str]] = (),
    today: date | None = None,
) -> list[Suggestion]:
    """`confirmed` holds `(kind, name)` of the user's existing items (kind is `income` or `bill`);
    those are not suggested again. Rows dated after `today` are ignored."""
    known = {(kind, normalise_merchant(name)) for kind, name in confirmed}
    groups: dict[tuple[str, str], list[tuple[date, int, str]]] = defaultdict(list)
    for row in rows:
        if _candidate(row) and (today is None or as_date(row["date"]) <= today):
            key = (row["type"], normalise_merchant(row["description"]))
            groups[key].append((as_date(row["date"]), int(row["amount_sen"]), row["description"]))

    found = []
    for (direction, name), events in groups.items():
        kind = "income" if direction == "income" else "bill"
        if len(events) < MIN_OCCURRENCES or (kind, name) in known:
            continue
        events.sort(key=lambda e: (e[0], e[1], e[2]))
        dates = [e[0] for e in events]
        gaps = [(b - a).days for a, b in zip(dates, dates[1:], strict=False)]
        cadence = _cadence(gaps)
        amounts = _amount_stats([e[1] for e in events])
        if cadence is None or amounts is None:
            continue
        label, gap_share = cadence
        amount, amount_share, spread = amounts
        found.append(
            Suggestion(
                name=name,
                display_name=events[-1][2],
                kind=kind,
                amount_sen=amount,
                cadence=label,
                anchor_date=dates[-1],
                confidence=round(gap_share * amount_share * (1 - min(1.0, spread)), 4),
                occurrences=len(events),
            )
        )
    return sorted(found, key=lambda s: (s.name, s.kind))
