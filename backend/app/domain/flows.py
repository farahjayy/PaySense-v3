"""What each transaction means for cash flow — the single definition shared by the month summary
and (in P4) Engine 1's weekly series, so the two can never disagree (ADR D-27, plan D-29).

  income    money in that counts as income
  spend     money out that counts as spending (BNPL instalments included: it is real cash out)
  refund    money back for a purchase: netted against spend, never counted as income
  transfer  an own-account move: ignored in both directions
  savings   money set aside: reported, but neither income nor spend
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from app.domain.categorize import REFUND, TRANSFER

Flow = Literal["income", "spend", "refund", "transfer", "savings"]


@dataclass(frozen=True)
class MonthSummary:
    month: str  # "YYYY-MM"
    income_sen: int
    spend_sen: int  # gross spend less refunds, never below zero
    refund_sen: int
    savings_sen: int
    net_sen: int  # income - spend


@dataclass(frozen=True)
class HistorySpan:
    first_date: date
    last_date: date
    distinct_months: int  # calendar months containing at least one non-transfer transaction
    span_days: int  # first to last, inclusive
    days_since_last: int


def as_date(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value[:10])


def classify(txn: Mapping[str, Any]) -> Flow:
    category = txn.get("category")
    if category == TRANSFER:
        return "transfer"
    if category == REFUND:
        return "refund"
    kind = txn["type"]
    if kind == "savings":
        return "savings"
    return "income" if kind == "income" else "spend"


def month_summary(txns: Iterable[Mapping[str, Any]]) -> list[MonthSummary]:
    """Per calendar month, ascending. Months holding only transfers still appear (as zeros)."""
    totals: dict[str, dict[str, int]] = {}
    for row in txns:
        month = as_date(row["date"]).strftime("%Y-%m")
        bucket = totals.setdefault(month, {"income": 0, "spend": 0, "refund": 0, "savings": 0})
        flow = classify(row)
        if flow != "transfer":
            bucket[flow] += row["amount_sen"]
    summary = []
    for month in sorted(totals):
        bucket = totals[month]
        spend = max(bucket["spend"] - bucket["refund"], 0)
        summary.append(
            MonthSummary(
                month=month,
                income_sen=bucket["income"],
                spend_sen=spend,
                refund_sen=bucket["refund"],
                savings_sen=bucket["savings"],
                net_sen=bucket["income"] - spend,
            )
        )
    return summary


def history_span(txns: Iterable[Mapping[str, Any]], today: date) -> HistorySpan | None:
    """How much history exists. The 4-month gate itself is applied by Engine 1 (P4)."""
    dates = [as_date(r["date"]) for r in txns if classify(r) != "transfer"]
    if not dates:
        return None
    first, last = min(dates), max(dates)
    return HistorySpan(
        first_date=first,
        last_date=last,
        distinct_months=len({(d.year, d.month) for d in dates}),
        span_days=(last - first).days + 1,
        days_since_last=(today - last).days,
    )
