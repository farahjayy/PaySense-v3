"""Insights (WP13, WP14): bill analysis and spending insights, built only from the user's own
ledger, recurring items and plan schedules. No model: plain arithmetic the user can check."""

import datetime as dt
from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from app.api.deps import CurrentUser, DbDep
from app.api.schemas import PROTECTED_RESPONSES, ApiModel
from app.api.summary import MonthParam
from app.core.errors import api_error

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
    savings_sen: int
    saved_sen: int = Field(description="Income less spending; the 'left over' of the month")
    savings_rate: float | None = Field(description="saved / income; None when there is no income")
    headline: str
    headline_rule: str
    categories: list[CategoryChangeOut]
    movers: list[CategoryChangeOut]
    unusual: list[UnusualTransactionOut]
    unusual_note: str | None
    mad_k: float


def _not_built():
    return api_error(501, "not_implemented", "This is not available yet.")


@router.get("/bills", response_model=BillAnalysisOut)
def bill_analysis(user: CurrentUser, db: DbDep) -> BillAnalysisOut:
    raise _not_built()


@router.get("/spending", response_model=SpendingInsightsOut)
def spending_insights(month: MonthParam, user: CurrentUser, db: DbDep) -> SpendingInsightsOut:
    raise _not_built()
