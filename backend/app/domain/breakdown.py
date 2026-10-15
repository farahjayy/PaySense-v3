"""Where one month's money went, by category (ADR D-45).

Built on `flows.classify`, the single definition of what counts as income, spending, a refund, a
transfer or savings, so the total here is always the month summary's total. A transfer between
the person's own accounts is ignored, a refund is taken off the total (it is not a category), and
savings are reported beside spending, never inside it.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.domain.flows import as_date, classify

SHARE_DIGITS = 4


@dataclass(frozen=True)
class CategorySpend:
    category: str
    spend_sen: int
    count: int
    share: float  # this category's part of gross category spending, 0 to 1


@dataclass(frozen=True)
class MonthBreakdown:
    month: str  # "YYYY-MM"
    income_sen: int
    spend_sen: int  # gross spending less refunds, never below zero: the month summary's figure
    gross_spend_sen: int  # what the category rows add up to
    refund_sen: int
    savings_sen: int
    categories: tuple[CategorySpend, ...]


def category_breakdown(txns: Iterable[Mapping[str, Any]], month: str) -> MonthBreakdown:
    income = refund = savings = 0
    spend: dict[str, list[int]] = {}  # category -> [total sen, number of rows]
    for row in txns:
        if as_date(row["date"]).strftime("%Y-%m") != month:
            continue
        flow = classify(row)
        amount = row["amount_sen"]
        if flow == "income":
            income += amount
        elif flow == "refund":
            refund += amount
        elif flow == "savings":
            savings += amount
        elif flow == "spend":
            bucket = spend.setdefault(row["category"], [0, 0])
            bucket[0] += amount
            bucket[1] += 1
    gross = sum(total for total, _ in spend.values())
    ranked = sorted(spend.items(), key=lambda item: (-item[1][0], item[0]))
    return MonthBreakdown(
        month=month,
        income_sen=income,
        spend_sen=max(gross - refund, 0),
        gross_spend_sen=gross,
        refund_sen=refund,
        savings_sen=savings,
        categories=tuple(
            CategorySpend(name, total, count, round(total / gross, SHARE_DIGITS))
            for name, (total, count) in ranked
        ),
    )
