"""Insights (WP13, WP14): bill analysis and spending insights, built only from the user's own
ledger, recurring items and plan schedules. No model: plain arithmetic the user can check."""

import datetime as dt
from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import Field

from app.api.deps import CurrentUser, DbDep, TodayDep
from app.api.schemas import PROTECTED_RESPONSES, ApiModel
from app.api.summary import MonthParam
from app.db import plans as plans_repo
from app.db import recurring_items, transactions
from app.domain.bill_analysis import analyse_bills
from app.domain.insights import HISTORY_MONTHS, spending_insights

router = APIRouter(prefix="/insights", tags=["insights"], responses=PROTECTED_RESPONSES)

DueKind = Literal["bill", "instalment"]


class RecurringBillOut(ApiModel):
    item_id: str
    name: str
    amount_sen: int
    cadence: Literal["weekly", "biweekly", "monthly", "semester", "custom"]
    monthly_sen: int = Field(description="The bill's cost per month, from its cadence")


class RecurringSummaryOut(ApiModel):
    count: int
    monthly_total_sen: int
    monthly_income_sen: int | None = Field(description="Confirmed recurring income per month")
    bills_share: float | None = Field(description="Bills as a share of that recurring income")
    items: list[RecurringBillOut]


class BillIncreaseOut(ApiModel):
    item_id: str
    name: str
    previous_sen: int
    latest_sen: int
    change_sen: int
    change_pct: float
    previous_date: dt.date
    latest_date: dt.date


class DueItemOut(ApiModel):
    kind: DueKind
    name: str
    due_date: dt.date
    amount_sen: int
    overdue: bool = Field(description="An unpaid instalment whose date has passed: due now")
    provider_label: str | None = None
    plan_id: str | None = None
    seq: int | None = None
    item_id: str | None = None


class CollisionOut(ApiModel):
    start: dt.date
    end: dt.date
    total_sen: int
    items: list[DueItemOut]


class BillAnalysisOut(ApiModel):
    as_of: dt.date
    window_days: int
    collision_window_days: int
    recurring: RecurringSummaryOut
    increases: list[BillIncreaseOut]
    collisions: list[CollisionOut]
    upcoming: list[DueItemOut]
    upcoming_total_sen: int


ChangeStatus = Literal["new", "gone", "up", "down", "same"]


class CategoryChangeOut(ApiModel):
    category: str
    spend_sen: int
    previous_sen: int
    change_sen: int
    change_pct: float | None = Field(description="None when the category is new this month")
    status: ChangeStatus


class UnusualTransactionOut(ApiModel):
    transaction_id: str
    date: dt.date
    category: str
    description: str | None
    amount_sen: int
    median_sen: int
    threshold_sen: int


class SpendingInsightsOut(ApiModel):
    month: str
    previous_month: str | None
    income_sen: int
    spend_sen: int
    savings_sen: int = Field(description="Money logged as Savings (set aside, D-45)")
    left_over_sen: int = Field(description="Income less spending")
    savings_rate: float | None = Field(
        description="left_over / income; None when there is no income"
    )
    set_aside_rate: float | None = Field(description="savings_sen / income")
    headline: str
    headline_rule: str
    categories: list[CategoryChangeOut]
    movers: list[CategoryChangeOut]
    unusual: list[UnusualTransactionOut]
    unusual_note: str | None
    mad_k: float


def bills_for(db: Any, user_id: str, today: dt.date) -> BillAnalysisOut:
    """Shared by the route and the assistant's `get_bill_analysis` tool."""
    result = analyse_bills(
        recurring_items.list_items(db, user_id, active_only=True),
        plans_repo.list_with_instalments(db, user_id),
        transactions.list_for_forecast(db, user_id, today),
        today,
    )
    return BillAnalysisOut.model_validate(asdict(result))


@router.get("/bills", response_model=BillAnalysisOut)
def bill_analysis(user: CurrentUser, db: DbDep, today: TodayDep) -> BillAnalysisOut:
    """Recurring bills, bills that went up, the next 30 days and where payments collide."""
    return bills_for(db, user.id, today)


def spending_for(db: Any, user_id: str, month: str) -> SpendingInsightsOut:
    """Shared by the route and the assistant's `get_spending_insights` tool."""
    year, number = int(month[:4]), int(month[5:7])
    index = year * 12 + number - 1
    first = dt.date((index - HISTORY_MONTHS) // 12, (index - HISTORY_MONTHS) % 12 + 1, 1)
    last = dt.date(year + number // 12, number % 12 + 1, 1) - dt.timedelta(days=1)
    rows = transactions.list_between(db, user_id, first, last, newest_first=False)
    return SpendingInsightsOut.model_validate(asdict(spending_insights(rows, month)))


@router.get("/spending", response_model=SpendingInsightsOut)
def spending(month: MonthParam, user: CurrentUser, db: DbDep) -> SpendingInsightsOut:
    """Month-on-month changes by category, unusual transactions, the savings rate, a headline."""
    return spending_for(db, user.id, month)
