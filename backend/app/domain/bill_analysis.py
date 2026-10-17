"""Bill analysis (WP13): what the person's confirmed bills cost a month, which went up, what is due
in the next 30 days, and where several payments land in the same week. Plain arithmetic over
confirmed recurring items, the ledger and plan schedules; nothing here is forecast.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

from app.domain.flows import as_date
from app.domain.merchants import normalise_merchant
from app.engines.forecasting.flows import occurrences

DueKind = Literal["bill", "instalment"]
WINDOW_DAYS = 30
COLLISION_DAYS = 7
DAYS_PER_YEAR = 365.25
MONTHS_PER_YEAR = 12
PER_MONTH = {"monthly": 1.0, "weekly": 52 / 12, "biweekly": 26 / 12, "semester": 1 / 6}
SHARE_DIGITS = 4


@dataclass(frozen=True)
class RecurringBill:
    item_id: str
    name: str
    amount_sen: int
    cadence: str
    monthly_sen: int


@dataclass(frozen=True)
class RecurringSummary:
    count: int
    monthly_total_sen: int
    monthly_income_sen: int | None
    bills_share: float | None
    items: list[RecurringBill]


@dataclass(frozen=True)
class BillIncrease:
    item_id: str
    name: str
    previous_sen: int
    latest_sen: int
    change_sen: int
    change_pct: float
    previous_date: date
    latest_date: date


@dataclass(frozen=True)
class DueItem:
    kind: DueKind
    name: str
    due_date: date
    amount_sen: int
    overdue: bool = False
    provider_label: str | None = None
    plan_id: str | None = None
    seq: int | None = None
    item_id: str | None = None


@dataclass(frozen=True)
class Collision:
    start: date
    end: date
    total_sen: int
    items: list[DueItem]


@dataclass(frozen=True)
class BillAnalysis:
    as_of: date
    recurring: RecurringSummary
    increases: list[BillIncrease]
    collisions: list[Collision]
    upcoming: list[DueItem]
    upcoming_total_sen: int
    window_days: int = WINDOW_DAYS
    collision_window_days: int = COLLISION_DAYS
    notes: list[str] = field(default_factory=list)


def monthly_cost(item: Mapping[str, Any]) -> int:
    """What a recurring item costs (or brings in) per month, from its cadence."""
    amount = int(item["amount_sen"])
    if item["cadence"] == "custom":
        return round(amount * (DAYS_PER_YEAR / MONTHS_PER_YEAR) / int(item["custom_interval_days"]))
    return round(amount * PER_MONTH[item["cadence"]])


def _is_occurrence(item: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    """A ledger row is a payment of this item: linked to it, or the same type and merchant text
    (the rule Engine 1 uses to cover a confirmed item, `unlogged_occurrences_net`)."""
    if row.get("recurring_item_id") and row.get("recurring_item_id") == item.get("id"):
        return True
    wanted = "expense" if item["kind"] == "bill" else "income"
    text = normalise_merchant(item.get("match_text") or item["name"])
    return (
        bool(text) and row["type"] == wanted and normalise_merchant(row.get("description")) == text
    )


def _increase(item: Mapping[str, Any], rows: Iterable[Mapping[str, Any]]) -> BillIncrease | None:
    paid = sorted(
        ((as_date(r["date"]), int(r["amount_sen"])) for r in rows if _is_occurrence(item, r)),
        key=lambda pair: pair[0],
    )
    if len(paid) < 2:
        return None
    (before, previous), (after, latest) = paid[-2], paid[-1]
    if latest <= previous:
        return None
    return BillIncrease(
        item_id=str(item["id"]),
        name=item["name"],
        previous_sen=previous,
        latest_sen=latest,
        change_sen=latest - previous,
        change_pct=round((latest - previous) / previous, SHARE_DIGITS),
        previous_date=before,
        latest_date=after,
    )


def _due_items(
    bills: list[Mapping[str, Any]], plans: Iterable[Mapping[str, Any]], today: date
) -> list[DueItem]:
    last = today + timedelta(days=WINDOW_DAYS - 1)
    due: list[DueItem] = [
        DueItem(
            kind="bill",
            name=item["name"],
            due_date=day,
            amount_sen=int(item["amount_sen"]),
            item_id=str(item["id"]),
        )
        for item in bills
        for day in occurrences(item, today, last)
    ]
    for plan in plans:
        for inst in plan["installments"]:
            day = as_date(inst["due_date"])
            if inst["is_paid"] or day > last:
                continue
            due.append(
                DueItem(
                    kind="instalment",
                    name=plan["item_name"],
                    due_date=day,
                    amount_sen=int(inst["amount_sen"]),
                    overdue=day < today,
                    provider_label=plan.get("provider_label"),
                    plan_id=str(plan["id"]),
                    seq=int(inst["seq"]),
                )
            )
    return sorted(due, key=lambda d: (d.due_date, d.kind, d.name))


def _collisions(due: list[DueItem]) -> list[Collision]:
    """Greedy 7-day windows over the upcoming (not overdue) items; two or more in a window is a
    collision. Every item belongs to exactly one window."""
    upcoming = [d for d in due if not d.overdue]
    found: list[Collision] = []
    i = 0
    while i < len(upcoming):
        start = upcoming[i].due_date
        end = start + timedelta(days=COLLISION_DAYS - 1)
        group = [d for d in upcoming[i:] if d.due_date <= end]
        if len(group) >= 2:
            found.append(Collision(start, end, sum(d.amount_sen for d in group), group))
        i += len(group)
    return found


def analyse_bills(
    items: Iterable[Mapping[str, Any]],
    plans: Iterable[Mapping[str, Any]],
    rows: Iterable[Mapping[str, Any]],
    today: date,
) -> BillAnalysis:
    active = [i for i in items if i.get("active", True)]
    bills = [i for i in active if i["kind"] == "bill"]
    incomes = [i for i in active if i["kind"] == "income"]
    rows = list(rows)
    recurring = [
        RecurringBill(
            item_id=str(i["id"]),
            name=i["name"],
            amount_sen=int(i["amount_sen"]),
            cadence=i["cadence"],
            monthly_sen=monthly_cost(i),
        )
        for i in sorted(bills, key=lambda i: i["name"].casefold())
    ]
    total = sum(r.monthly_sen for r in recurring)
    income = sum(monthly_cost(i) for i in incomes) if incomes else None
    share = round(total / income, SHARE_DIGITS) if income else None
    due = _due_items(bills, list(plans), today)
    increases = [inc for i in bills if (inc := _increase(i, rows)) is not None]
    return BillAnalysis(
        as_of=today,
        recurring=RecurringSummary(len(recurring), total, income, share, recurring),
        increases=sorted(increases, key=lambda inc: -inc.change_sen),
        collisions=_collisions(due),
        upcoming=due,
        upcoming_total_sen=sum(d.amount_sen for d in due),
    )
