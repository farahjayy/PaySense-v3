"""Known flows placed in the month of their exact date (plan P4, task C4; PRD 3.1).

Confirmed recurring income and bills, every unpaid BNPL instalment, and the cash outlay of a plan
under evaluation are not forecast: they are expanded from their rules onto calendar dates and
summed per month. An unpaid instalment that is already overdue is due now, so it lands in the first
month of the horizon.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol

from app.domain.flows import as_date
from app.domain.merchants import normalise_merchant
from app.domain.schedule import add_months

FIXED_STEP_DAYS = {"weekly": 7, "biweekly": 14}
SEMESTER_MONTHS = 6
MONTHS_PER_YEAR = 12


class _Instalment(Protocol):
    seq: int
    due_date: date
    amount_sen: int
    paid_at_checkout: bool


class ProposedPlan(Protocol):
    purchase_date: date
    cash_at_purchase_sen: int
    instalments: Iterable[_Instalment]


@dataclass
class MonthFlows:
    income_sen: int = 0
    bills_sen: int = 0
    instalments_sen: int = 0


def month_key(day: date) -> str:
    return day.strftime("%Y-%m")


def _months(start: date, end: date) -> list[str]:
    keys, cursor = [], date(start.year, start.month, 1)
    while cursor <= end:
        keys.append(month_key(cursor))
        cursor = date(cursor.year + (cursor.month == MONTHS_PER_YEAR), cursor.month % 12 + 1, 1)
    return keys


def occurrences(item: Mapping[str, Any], start: date, end: date) -> list[date]:
    """Dates in [start, end] on which a recurring item falls."""
    anchor = as_date(item["anchor_date"])
    cadence = item["cadence"]
    days: list[date] = []
    if cadence in ("monthly", "semester"):
        step = 1 if cadence == "monthly" else SEMESTER_MONTHS
        behind = (start.year - anchor.year) * MONTHS_PER_YEAR + start.month - anchor.month
        n = max(0, behind // step - 1)
        while (day := add_months(anchor, n * step)) <= end:
            if day >= start:
                days.append(day)
            n += 1
        return days
    step_days = FIXED_STEP_DAYS.get(cadence) or int(item["custom_interval_days"])
    behind_days = (start - anchor).days
    n = max(0, -(-behind_days // step_days))  # ceiling: the first occurrence on or after start
    while (day := anchor + timedelta(days=n * step_days)) <= end:
        days.append(day)
        n += 1
    return days


def known_flows(
    items: Iterable[Mapping[str, Any]],
    plans: Iterable[Mapping[str, Any]],
    start: date,
    end: date,
    proposed: ProposedPlan | None = None,
) -> dict[str, MonthFlows]:
    """Per-month known flows over [start, end] (every month present, in order)."""
    flows = {key: MonthFlows() for key in _months(start, end)}

    for item in items:
        if not item.get("active", True):
            continue
        for day in occurrences(item, start, end):
            bucket = flows[month_key(day)]
            if item["kind"] == "income":
                bucket.income_sen += int(item["amount_sen"])
            else:
                bucket.bills_sen += int(item["amount_sen"])

    first_month = month_key(start)
    for plan in plans:
        for instalment in plan["installments"]:
            if instalment["is_paid"]:
                continue
            due = as_date(instalment["due_date"])
            if due > end:
                continue
            key = first_month if due < start else month_key(due)  # overdue means due now
            flows[key].instalments_sen += int(instalment["amount_sen"])

    if proposed is not None:
        if start <= proposed.purchase_date <= end:
            flows[
                month_key(proposed.purchase_date)
            ].instalments_sen += proposed.cash_at_purchase_sen
        for instalment in proposed.instalments:
            if instalment.paid_at_checkout or not start <= instalment.due_date <= end:
                continue  # a checkout instalment is already in cash_at_purchase_sen
            flows[month_key(instalment.due_date)].instalments_sen += instalment.amount_sen
    return flows


MATCH_TOLERANCE_DAYS = 7  # an actual payment this close to its scheduled day counts as that payment


def unlogged_occurrences_net(
    items: Iterable[Mapping[str, Any]],
    rows: Iterable[Mapping[str, Any]],
    first_day: date,
    until: date,
) -> int:
    """Income minus bills for confirmed items that were due in [first_day, until) but have no
    matching logged transaction. A confirmed allowance or rent that the user simply has not entered
    yet is assumed to have happened, instead of leaving a hole in the month."""
    logged = [
        (normalise_merchant(r.get("description")), as_date(r["date"]))
        for r in rows
        if first_day <= as_date(r["date"]) < until
    ]
    net = 0
    for item in items:
        if not item.get("active", True):
            continue
        text = normalise_merchant(item.get("match_text") or item["name"])
        for due in occurrences(item, first_day, until - timedelta(days=1)):
            seen = any(
                name == text and abs((day - due).days) <= MATCH_TOLERANCE_DAYS
                for name, day in logged
            )
            if not seen:
                amount = int(item["amount_sen"])
                net += amount if item["kind"] == "income" else -amount
    return net
