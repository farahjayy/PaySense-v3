"""The two weekly series Engine 1 forecasts (plan P4, task C2).

* spend: expenses that are not a confirmed recurring item, not a BNPL plan payment, not a
  transfer and not savings; refunds net against the week's spend (never below zero).
* income: income that is not covered by a confirmed recurring income. A refund is not income.

Weeks run Monday to Sunday and only complete weeks are used: a half-observed first week would look
like a spending drop, and the current week is still in progress. The series also stops at the last
logged day, so a user who stopped logging does not look like a user who stopped spending. A
week with nothing in it is an explicit zero. Everything is integer sen.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np

from app.domain.categorize import BNPL, REFUND, TRANSFER
from app.domain.flows import as_date
from app.domain.merchants import normalise_merchant

DAYS_PER_WEEK = 7
MONDAY_FIRST_GAP_MESSAGE = "the first partial week is dropped"


@dataclass(frozen=True)
class WeeklySeries:
    start: date | None  # the Monday of the first complete week; None when there is none
    spend: np.ndarray  # integer sen per week
    income: np.ndarray

    @property
    def weeks(self) -> int:
        return len(self.spend)


def _is_covered(row: Mapping[str, Any], covered: set[tuple[str, str]]) -> bool:
    return (
        bool(row.get("recurring_item_id"))
        or (
            row["type"],
            normalise_merchant(row.get("description")),
        )
        in covered
    )


def _is_plan_payment(row: Mapping[str, Any]) -> bool:
    return bool(
        row.get("bnpl_plan_id")
        or row.get("bnpl_installment_id")
        or row.get("is_bnpl")
        or row.get("category") == BNPL
    )


def build_weekly_series(
    rows: Iterable[Mapping[str, Any]],
    today: date,
    covered: Iterable[tuple[str, str]] = (),
) -> WeeklySeries:
    """`covered` holds `(type, merchant text)` of confirmed recurring items; a transaction whose
    own `recurring_item_id` is set is covered as well."""
    keys = {(kind, normalise_merchant(text)) for kind, text in covered}
    keys = {(kind, text) for kind, text in keys if text}  # a nameless item matches nothing
    events: list[tuple[date, str, int]] = []
    latest: date | None = None  # the last day anything at all was logged
    for row in rows:
        day = as_date(row["date"])
        if day < today and (latest is None or day > latest):
            latest = day
        amount = int(row["amount_sen"])
        category = row.get("category")
        if category == TRANSFER or row["type"] == "savings":
            continue
        if category == REFUND:
            events.append((day, "refund", amount))
        elif _is_plan_payment(row) or _is_covered(row, keys):
            continue
        elif row["type"] == "expense":
            events.append((day, "spend", amount))
        elif row["type"] == "income":
            events.append((day, "income", amount))
    if not events:
        return WeeklySeries(None, np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64))

    first = min(day for day, _, _ in events)
    monday = first + timedelta(days=(-first.weekday()) % DAYS_PER_WEEK)
    last = today - timedelta(days=1)  # today's week is in progress
    if latest is not None:
        last = min(last, latest)  # weeks after the last logged day were never observed
    sunday = last - timedelta(days=(last.weekday() + 1) % DAYS_PER_WEEK)
    weeks = ((sunday - monday).days + 1) // DAYS_PER_WEEK
    if weeks < 1:
        return WeeklySeries(None, np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64))

    spend = np.zeros(weeks, dtype=np.int64)
    refund = np.zeros(weeks, dtype=np.int64)
    income = np.zeros(weeks, dtype=np.int64)
    target = {"spend": spend, "refund": refund, "income": income}
    for day, kind, amount in events:
        index = (day - monday).days // DAYS_PER_WEEK
        if 0 <= index < weeks:
            target[kind][index] += amount
    return WeeklySeries(monday, np.maximum(spend - refund, 0), income)
