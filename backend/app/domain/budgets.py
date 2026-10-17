"""Category budgets (WP2): which categories can have one, how a month stands against them, and a
suggested set of limits worked out from the person's own money. Plain arithmetic, no model.

"Spent" is the month summary's definition (ADR D-45, via `category_breakdown`), so a budget bar,
the spending panel and the month summary can never disagree. The suggestion takes the known flows
of the month from Engine 1 (`known_flows`) and Engine 1's own rule for what discretionary spending
is (`classify_row`), so it never re-implements either.
"""

import calendar
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from app.domain.breakdown import category_breakdown
from app.domain.categories import CHANGES_THE_MATHS, locked_name
from app.domain.flows import as_date, month_summary
from app.engines.forecasting.flows import known_flows
from app.engines.forecasting.series import classify_row, covered_keys
from app.engines.forecasting.service import confirmed_covered

State = Literal["ok", "near", "over"]
IncomeBasis = Literal["recurring", "average", "none"]

# ASSUMED 20 (WP2): a budget is "near" from 80% of its limit and "over" from 100%.
NEAR_AT = 0.8
OVER_AT = 1.0
# ASSUMED 20 (WP2): the suggestion keeps 10% of income back before splitting what is left.
BUFFER_RATE = 0.10
ROUND_TO_SEN = 500  # suggested limits are whole RM5, rounded down
HISTORY_MONTHS = 3  # complete months the suggestion learns category shares from
INCOME_CATEGORIES = frozenset({"Salary", "Allowance"})
MAX_CATEGORY_LENGTH = 60  # a transaction's category limit (api/transactions.py)
_INVISIBLE = frozenset({"Cc", "Cf", "Co", "Cs", "Cn"})
PERCENT_DIGITS = 4


# ------------------------------------------------------------------ category rules
def budget_category(raw: object) -> str:
    """The category name a budget is stored under; ValueError with a sentence if it cannot have
    one. Built-in names are spelled the app's way, own names kept as typed (ADR D-43). A name may
    be as long as a transaction's category (60), since imported files can carry long ones."""
    if not isinstance(raw, str):
        raise ValueError("Give the budget a category.")
    builtin = locked_name(raw)
    if builtin in CHANGES_THE_MATHS:
        raise ValueError(f"{builtin} cannot have a budget: it is not ordinary spending.")
    if builtin in INCOME_CATEGORIES:
        raise ValueError(f"{builtin} is an income category; budgets are for spending.")
    if builtin:
        return builtin
    if any(unicodedata.category(ch) in _INVISIBLE for ch in raw):
        raise ValueError("A category name cannot contain line breaks or invisible characters.")
    name = " ".join(raw.split())
    if not any(ch.isalpha() for ch in name):
        raise ValueError("A category name needs at least one letter.")
    if len(name) > MAX_CATEGORY_LENGTH:
        raise ValueError(f"A category name can be at most {MAX_CATEGORY_LENGTH} characters.")
    return name


def state_of(percent: float) -> State:
    if percent >= OVER_AT:
        return "over"
    if percent >= NEAR_AT:
        return "near"
    return "ok"


def _month_bounds(month: str) -> tuple[date, date]:
    year, number = int(month[:4]), int(month[5:7])
    return date(year, number, 1), date(year, number, calendar.monthrange(year, number)[1])


# ------------------------------------------------------------------ status
@dataclass(frozen=True)
class BudgetStatusItem:
    category: str
    limit_sen: int
    spent_sen: int
    remaining_sen: int
    percent: float
    state: State
    projected_sen: int | None
    projected_state: State | None


@dataclass(frozen=True)
class BudgetStatus:
    month: str
    is_current: bool
    days_in_month: int
    days_elapsed: int
    items: list[BudgetStatusItem]
    total_limit_sen: int
    total_spent_sen: int
    unbudgeted_spend_sen: int
    refund_sen: int
    month_spend_sen: int
    near_at: float = NEAR_AT
    over_at: float = OVER_AT


def budget_status(
    budgets: Iterable[Mapping[str, Any]],
    txns: Iterable[Mapping[str, Any]],
    month: str,
    today: date,
) -> BudgetStatus:
    """How `month` stands against each budget. Projection only for the month containing today."""
    first, last = _month_bounds(month)
    breakdown = category_breakdown(txns, month)
    spent_by = {c.category.casefold(): c.spend_sen for c in breakdown.categories}
    is_current = first <= today <= last
    if today > last:
        elapsed = last.day
    elif today < first:
        elapsed = 0
    else:
        elapsed = today.day
    items: list[BudgetStatusItem] = []
    budgeted: set[str] = set()
    for row in sorted(budgets, key=lambda r: r["category"].casefold()):
        key = row["category"].casefold()
        budgeted.add(key)
        limit = int(row["limit_sen"])
        spent = spent_by.get(key, 0)
        percent = round(spent / limit, PERCENT_DIGITS)
        projected = projected_state = None
        if is_current and elapsed > 0:
            projected = spent * last.day // elapsed
            projected_state = state_of(projected / limit)
        items.append(
            BudgetStatusItem(
                category=row["category"],
                limit_sen=limit,
                spent_sen=spent,
                remaining_sen=limit - spent,
                percent=percent,
                state=state_of(spent / limit),
                projected_sen=projected,
                projected_state=projected_state,
            )
        )
    return BudgetStatus(
        month=month,
        is_current=is_current,
        days_in_month=last.day,
        days_elapsed=elapsed,
        items=items,
        total_limit_sen=sum(i.limit_sen for i in items),
        total_spent_sen=sum(i.spent_sen for i in items),
        unbudgeted_spend_sen=sum(v for k, v in spent_by.items() if k not in budgeted),
        refund_sen=breakdown.refund_sen,
        month_spend_sen=breakdown.spend_sen,
    )


# ------------------------------------------------------------------ suggestion
@dataclass(frozen=True)
class SuggestedBudget:
    category: str
    share: float
    recent_monthly_sen: int
    limit_sen: int


@dataclass(frozen=True)
class BudgetSuggestion:
    month: str
    income_sen: int
    income_basis: IncomeBasis
    bills_sen: int
    instalments_sen: int
    buffer_sen: int
    buffer_rate: float
    pool_sen: int
    months_used: list[str]
    items: list[SuggestedBudget]
    notes: list[str] = field(default_factory=list)


def _history_months(rows: Sequence[Mapping[str, Any]], month: str) -> list[str]:
    """Up to HISTORY_MONTHS complete calendar months before `month` that hold any transaction."""
    seen = sorted({as_date(r["date"]).strftime("%Y-%m") for r in rows})
    return [m for m in seen if m < month][-HISTORY_MONTHS:]


def suggest_budget(
    items: Iterable[Mapping[str, Any]],
    plans: Iterable[Mapping[str, Any]],
    txns: Iterable[Mapping[str, Any]],
    month: str,
    today: date,
) -> BudgetSuggestion:
    """Income − confirmed bills − instalments due − a buffer = the pool, split by each category's
    share of recent discretionary spending, each limit rounded down to RM5."""
    first, last = _month_bounds(month)
    items, rows = list(items), list(txns)
    known = known_flows(items, list(plans), first, last)[month]
    notes: list[str] = []
    used = _history_months(rows, month)

    income, basis = known.income_sen, "recurring"
    if income <= 0:
        summaries = [m for m in month_summary(rows) if m.month in used]
        if summaries:
            income = round(sum(m.income_sen for m in summaries) / len(summaries))
            basis = "average"
            notes.append(
                f"No confirmed recurring income falls in {month}; used your average income over "
                f"{len(summaries)} earlier month(s)."
            )
        else:
            income, basis = 0, "none"
            notes.append("No income is known yet, so there is nothing to split.")
    buffer = round(income * BUFFER_RATE)
    pool = max(income - known.bills_sen - known.instalments_sen - buffer, 0)
    if income > 0 and pool == 0:
        notes.append(
            "After bills, instalments and the buffer, nothing is left to budget this month."
        )

    keys = covered_keys(confirmed_covered(items))
    totals: dict[str, int] = {}
    for row in rows:
        if as_date(row["date"]).strftime("%Y-%m") in used and classify_row(row, keys) == "spend":
            totals[row["category"]] = totals.get(row["category"], 0) + int(row["amount_sen"])
    spend_total = sum(totals.values())
    suggested: list[SuggestedBudget] = []
    if pool > 0 and spend_total > 0:
        for category, total in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0])):
            try:
                name = budget_category(category)
            except ValueError:
                continue
            share = total / spend_total
            limit = int(pool * share) // ROUND_TO_SEN * ROUND_TO_SEN
            if limit <= 0:
                continue
            suggested.append(
                SuggestedBudget(
                    category=name,
                    share=round(share, PERCENT_DIGITS),
                    recent_monthly_sen=round(total / len(used)),
                    limit_sen=limit,
                )
            )
        dropped = len(totals) - len(suggested)
        if dropped:
            notes.append(f"{dropped} small categor{'y' if dropped == 1 else 'ies'} got under RM5.")
    elif pool > 0:
        notes.append("There is no recent spending to learn your categories from yet.")
    return BudgetSuggestion(
        month=month,
        income_sen=income,
        income_basis=basis,  # type: ignore[arg-type]
        bills_sen=known.bills_sen,
        instalments_sen=known.instalments_sen,
        buffer_sen=buffer,
        buffer_rate=BUFFER_RATE,
        pool_sen=pool,
        months_used=used,
        items=suggested,
        notes=notes,
    )
