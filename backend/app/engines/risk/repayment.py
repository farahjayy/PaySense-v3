"""Repayment-history flag: a rule over the user's own instalments, with no model behind it (D-11).

Why it is not a feature: whether someone paid late is evidence about the past that the simulated
label (will money run short?) does not contain, so putting it in the model would make the model
disagree with its own label. It is shown beside the probability instead, plainly separated.

Two different things are counted. A *missed* instalment is unpaid and past its due date, however
old: it is still owed. A *late* one was paid after its due date, looked at over the last six months
only. The warning level borrows Bank Negara Malaysia's personal-financing practice of suspending an
account after three consecutive missed payments (the team's research brief): three
missed instalments in a row on one plan is when the flag stops being a note and becomes a warning.
An instalment paid late is not missed, so late payments alone never reach the warning.
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
    "none": "No overdue instalments, and none paid late in the last six months.",
    "watch": (
        "You have overdue instalments, or instalments paid late in the last six months. This "
        "does not change the risk score, but it is worth clearing before you take on more."
    ),
    "warning": (
        "You have missed three or more instalments in a row on one plan. Bank Negara Malaysia's "
        "policy lets a provider suspend an account after three consecutive missed payments, so "
        "clear these before taking on another plan."
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


def _is_missed(row: Mapping[str, Any], today: date) -> bool:
    """Unpaid and past its due date. Not yet due, or due today, is never missed."""
    return not row["is_paid"] and as_date(row["due_date"]) < today


def _is_paid_late(row: Mapping[str, Any]) -> bool:
    if not row["is_paid"]:
        return False
    paid = row.get("paid_date")
    return paid is not None and as_date(paid) > as_date(row["due_date"])


def _longest_run(plan_rows: list[Mapping[str, Any]], today: date) -> int:
    best = run = 0
    for row in sorted(plan_rows, key=lambda r: r["seq"]):
        if as_date(row["due_date"]) > today:
            break  # later instalments are not yet due
        run = run + 1 if _is_missed(row, today) else 0
        best = max(best, run)
    return best


def assess_repayment(instalments: Iterable[Mapping[str, Any]], today: date) -> RepaymentFlag:
    """Flag from the user's instalments.

    Each row needs `plan_id`, `seq`, `due_date`, `amount_sen`, `is_paid`, `paid_date`. Missed
    instalments are counted whatever their age; late payments only if due within the last six
    months (inclusive of the same calendar day).
    """
    rows = list(instalments)
    start = add_months(today, -WINDOW_MONTHS)

    overdue = [r for r in rows if _is_missed(r, today)]
    late_paid = [r for r in rows if _is_paid_late(r) and start <= as_date(r["due_date"]) <= today]
    by_plan = groupby(
        sorted(rows, key=lambda r: (r["plan_id"], r["seq"])), key=lambda r: r["plan_id"]
    )
    longest = max((_longest_run(list(plan_rows), today) for _, plan_rows in by_plan), default=0)

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
