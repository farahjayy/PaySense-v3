"""Spending insights (WP14): how a month compares with the one before, what stood out, and how much
of the income was kept. Built only from the month summary and the category breakdown (ADR D-45),
so every total here equals the dashboard's. No model.
"""

import statistics
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from app.domain.breakdown import category_breakdown
from app.domain.categorize import BNPL
from app.domain.flows import as_date, classify
from app.domain.money import format_rm

ChangeStatus = Literal["new", "gone", "up", "down", "same"]
MOVERS = 3
# ASSUMED 23 (WP14): a row is unusual above median + k x 1.4826 x MAD of the person's own earlier
# rows in that category (k = 3: three robust standard deviations), judged only with 5+ earlier rows.
MAD_K = 3.0
MAD_TO_SD = 1.4826
MIN_HISTORY = 5
HISTORY_MONTHS = 24
# The headline's "category up" rule: at least this much more than last month, both ways.
UP_SHARE = 0.20
UP_MIN_SEN = 5_000
KEPT_SHARE = 0.20
RATE_DIGITS = 4


@dataclass(frozen=True)
class CategoryChange:
    category: str
    spend_sen: int
    previous_sen: int
    change_sen: int
    change_pct: float | None
    status: ChangeStatus


@dataclass(frozen=True)
class UnusualTransaction:
    transaction_id: str
    date: date
    category: str
    description: str | None
    amount_sen: int
    median_sen: int
    threshold_sen: int


@dataclass(frozen=True)
class SpendingInsights:
    month: str
    previous_month: str | None
    income_sen: int
    spend_sen: int
    savings_sen: int
    left_over_sen: int
    savings_rate: float | None
    set_aside_rate: float | None
    headline: str
    headline_rule: str
    categories: list[CategoryChange]
    movers: list[CategoryChange]
    unusual: list[UnusualTransaction]
    unusual_note: str | None
    mad_k: float = MAD_K


def _previous(month: str) -> str:
    year, number = int(month[:4]), int(month[5:7])
    return f"{year - 1}-12" if number == 1 else f"{year}-{number - 1:02d}"


def _whole_percent(ratio: float) -> str:
    return f"{int(Decimal(str(ratio * 100)).quantize(Decimal(1), ROUND_HALF_UP))}%"


def _changes(
    rows: list[Mapping[str, Any]], month: str, previous: str | None
) -> list[CategoryChange]:
    now = {c.category: c.spend_sen for c in category_breakdown(rows, month).categories}
    before = (
        {c.category: c.spend_sen for c in category_breakdown(rows, previous).categories}
        if previous
        else {}
    )
    out = []
    for name in sorted(set(now) | set(before)):
        spend, prior = now.get(name, 0), before.get(name, 0)
        if prior == 0:
            status: ChangeStatus = "new"
        elif spend == 0:
            status = "gone"
        else:
            status = "up" if spend > prior else "down" if spend < prior else "same"
        out.append(
            CategoryChange(
                category=name,
                spend_sen=spend,
                previous_sen=prior,
                change_sen=spend - prior,
                change_pct=round((spend - prior) / prior, RATE_DIGITS) if prior else None,
                status=status,
            )
        )
    return sorted(out, key=lambda c: (-c.spend_sen, c.category))


def _judged(row: Mapping[str, Any]) -> bool:
    """Discretionary spending can be unusual; a scheduled plan payment cannot."""
    return (
        classify(row) == "spend"
        and row.get("category") != BNPL
        and not row.get("is_bnpl")
        and not row.get("bnpl_plan_id")
    )


def _unusual(
    rows: list[Mapping[str, Any]], month: str
) -> tuple[list[UnusualTransaction], str | None]:
    first_day = date(int(month[:4]), int(month[5:7]), 1)
    history: dict[str, list[int]] = {}
    for row in rows:
        if _judged(row) and as_date(row["date"]) < first_day:
            history.setdefault(row["category"], []).append(int(row["amount_sen"]))
    flagged: list[UnusualTransaction] = []
    thin: set[str] = set()
    flat: set[str] = set()
    for row in rows:
        if not _judged(row) or as_date(row["date"]).strftime("%Y-%m") != month:
            continue
        earlier = history.get(row["category"], [])
        if len(earlier) < MIN_HISTORY:
            thin.add(row["category"])
            continue
        median = statistics.median(earlier)
        mad = statistics.median(abs(x - median) for x in earlier)
        if mad == 0:
            flat.add(row["category"])
            continue
        threshold = round(median + MAD_K * MAD_TO_SD * mad)
        if int(row["amount_sen"]) > threshold:
            flagged.append(
                UnusualTransaction(
                    transaction_id=str(row.get("id")),
                    date=as_date(row["date"]),
                    category=row["category"],
                    description=row.get("description"),
                    amount_sen=int(row["amount_sen"]),
                    median_sen=round(median),
                    threshold_sen=threshold,
                )
            )
    notes = []
    if thin:
        notes.append(f"Not enough history yet to judge {', '.join(sorted(thin))}.")
    if flat:
        notes.append(f"{', '.join(sorted(flat))} always cost the same, so nothing stands out.")
    return sorted(flagged, key=lambda u: -u.amount_sen), " ".join(notes) or None


def _headline(
    has_data: bool, income: int, spend: int, rate: float | None, changes: list[CategoryChange]
) -> tuple[str, str]:
    if not has_data:
        return "no_data", "Nothing is logged for this month yet."
    if income > 0 and spend > income:
        return "spent_more_than_income", (
            f"You spent {format_rm(spend - income)} more than came in this month."
        )
    ups = [
        c
        for c in changes
        if c.status == "up" and c.change_pct is not None and c.change_pct >= UP_SHARE
        and c.change_sen >= UP_MIN_SEN
    ]  # fmt: skip
    if ups:
        top = max(ups, key=lambda c: c.change_sen)
        return "category_up", (
            f"{top.category} spending is up {format_rm(top.change_sen)} on last month."
        )
    if rate is not None and rate >= KEPT_SHARE:
        return "kept_income", f"You kept {_whole_percent(rate)} of your income this month."
    downs = [c for c in changes if c.status in ("down", "gone")]
    if downs:
        top = min(downs, key=lambda c: c.change_sen)
        return "category_down", (
            f"{top.category} spending is down {format_rm(-top.change_sen)} on last month."
        )
    return "spent", f"You spent {format_rm(spend)} this month."


def spending_insights(txns: Iterable[Mapping[str, Any]], month: str) -> SpendingInsights:
    rows = list(txns)
    months = {as_date(r["date"]).strftime("%Y-%m") for r in rows}
    previous = _previous(month) if _previous(month) in months else None
    this = category_breakdown(rows, month)
    changes = _changes(rows, month, previous)
    movers = sorted(
        (c for c in changes if c.status != "same" and previous is not None),
        key=lambda c: (-abs(c.change_sen), c.category),
    )[:MOVERS]
    left_over = this.income_sen - this.spend_sen
    rate = round(left_over / this.income_sen, RATE_DIGITS) if this.income_sen else None
    set_aside = round(this.savings_sen / this.income_sen, RATE_DIGITS) if this.income_sen else None
    unusual, note = _unusual(rows, month)
    rule, headline = _headline(month in months, this.income_sen, this.spend_sen, rate, changes)
    return SpendingInsights(
        month=month,
        previous_month=previous,
        income_sen=this.income_sen,
        spend_sen=this.spend_sen,
        savings_sen=this.savings_sen,
        left_over_sen=left_over,
        savings_rate=rate,
        set_aside_rate=set_aside,
        headline=headline,
        headline_rule=rule,
        categories=changes,
        movers=movers,
        unusual=unusual,
        unusual_note=note,
    )
