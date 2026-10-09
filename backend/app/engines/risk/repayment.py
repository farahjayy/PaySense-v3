"""Repayment-history flag: a rule over the user's own instalments, with no model behind it (D-11).

Why it is not a feature: whether someone paid late is evidence about the past that the simulated
label (will money run short?) does not contain, so putting it in the model would make the model
disagree with its own label. It is shown beside the probability instead, plainly separated.

The warning level borrows Bank Negara Malaysia's personal-financing practice of acting after
three consecutive missed payments: three missed instalments in a row on one plan is the point at
which the flag stops being a note and becomes a warning.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from itertools import groupby
from typing import Any, Literal

from app.domain.flows import as_date
from app.domain.schedule import add_months

WINDOW_MONTHS = 6
CONSECUTIVE_MISSES_WARNING = 3

Level = Literal["none", "watch", "warning"]

_REASONS: dict[Level, str] = {
    "none": "No late or overdue instalments in the last six months.",
    "watch": (
        "You have late or overdue instalments in the last six months. This does not change the "
        "risk score, but it is worth clearing before you take on more."
    ),
    "warning": (
        "You have missed three or more instalments in a row on one plan. Bank Negara Malaysia "
        "treats three consecutive missed payments as the point where lenders may act, so clear "
        "these before taking on another plan."
    ),
}


@dataclass(frozen=True)
class RepaymentFlag:
    level: Level
    overdue_count: int
    overdue_sen: int
    late_paid_count: int
    longest_miss_run: int
    reason: str


def _is_miss(row: Mapping[str, Any], today: date) -> bool:
    """Overdue today, or paid after its due date. Not yet due is never a miss."""
    due = as_date(row["due_date"])
    if row["is_paid"]:
        paid = row.get("paid_date")
        return paid is not None and as_date(paid) > due
    return due < today


def _longest_run(plan_rows: list[Mapping[str, Any]], today: date) -> int:
    best = run = 0
    for row in sorted(plan_rows, key=lambda r: r["seq"]):
        if as_date(row["due_date"]) > today:
            break  # later instalments are not yet due
        run = run + 1 if _is_miss(row, today) else 0
        best = max(best, run)
    return best


def assess_repayment(instalments: Iterable[Mapping[str, Any]], today: date) -> RepaymentFlag:
    """Flag from instalments due in the last six months (inclusive of the same calendar day).

    Each row needs `plan_id`, `seq`, `due_date`, `amount_sen`, `is_paid`, `paid_date`.
    """
    start = add_months(today, -WINDOW_MONTHS)
    window = [r for r in instalments if start <= as_date(r["due_date"]) <= today]

    overdue = [r for r in window if not r["is_paid"] and as_date(r["due_date"]) < today]
    late_paid = [r for r in window if r["is_paid"] and _is_miss(r, today)]
    by_plan = groupby(
        sorted(window, key=lambda r: (r["plan_id"], r["seq"])), key=lambda r: r["plan_id"]
    )
    longest = max((_longest_run(list(rows), today) for _, rows in by_plan), default=0)

    level: Level = "none"
    if overdue or late_paid:
        level = "warning" if longest >= CONSECUTIVE_MISSES_WARNING else "watch"
    return RepaymentFlag(
        level=level,
        overdue_count=len(overdue),
        overdue_sen=sum(r["amount_sen"] for r in overdue),
        late_paid_count=len(late_paid),
        longest_miss_run=longest,
        reason=_REASONS[level],
    )
