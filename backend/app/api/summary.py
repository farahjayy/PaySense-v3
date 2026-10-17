"""Month summary (income / spend / net per month), how much history exists (ADR D-27), and where
one month's spending went by category (ADR D-45)."""

import calendar
import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbDep, TodayDep
from app.api.schemas import PROTECTED_RESPONSES, ApiModel
from app.db import transactions
from app.domain.breakdown import category_breakdown
from app.domain.flows import history_span, month_summary

router = APIRouter(prefix="/summary", tags=["summary"], responses=PROTECTED_RESPONSES)


class MonthOut(ApiModel):
    month: str
    income_sen: int
    spend_sen: int
    refund_sen: int
    savings_sen: int
    net_sen: int


class HistoryOut(ApiModel):
    first_date: dt.date
    last_date: dt.date
    distinct_months: int
    span_days: int
    days_since_last: int


class MonthSummaryOut(ApiModel):
    months: list[MonthOut]
    history: HistoryOut | None


@router.get("/months", response_model=MonthSummaryOut)
def months(user: CurrentUser, db: DbDep, today: TodayDep) -> MonthSummaryOut:
    return months_for(db, user.id, today)


def months_for(db: Any, user_id: str, today: dt.date) -> MonthSummaryOut:
    """Shared by the route and the assistant's `get_month_summary` tool."""
    rows = transactions.list_for_summary(db, user_id)
    span = history_span(rows, today)
    return MonthSummaryOut(
        months=[MonthOut(**vars(m)) for m in month_summary(rows)],
        history=HistoryOut(**vars(span)) if span else None,
    )


class CategorySpendOut(ApiModel):
    category: str
    spend_sen: int
    count: int
    share: float


class CategorySummaryOut(ApiModel):
    month: str
    income_sen: int
    spend_sen: int
    gross_spend_sen: int
    refund_sen: int
    savings_sen: int
    categories: list[CategorySpendOut]


# 2000 to 2100: the same span every date in the API is held to (api/types.py).
MonthParam = Annotated[str, Query(pattern=r"^(20\d{2}|2100)-(0[1-9]|1[0-2])$")]


@router.get("/categories", response_model=CategorySummaryOut)
def categories(month: MonthParam, user: CurrentUser, db: DbDep) -> CategorySummaryOut:
    """Spending by category for one calendar month, biggest first."""
    return categories_for(db, user.id, month)


def categories_for(db: Any, user_id: str, month: str) -> CategorySummaryOut:
    """Shared by the route and the assistant's `get_spending_by_category` tool."""
    year, number = int(month[:4]), int(month[5:])
    first = dt.date(year, number, 1)
    last = dt.date(year, number, calendar.monthrange(year, number)[1])
    rows = transactions.list_for_breakdown(db, user_id, first, last)
    result = category_breakdown(rows, month)
    return CategorySummaryOut(
        month=result.month,
        income_sen=result.income_sen,
        spend_sen=result.spend_sen,
        gross_spend_sen=result.gross_spend_sen,
        refund_sen=result.refund_sen,
        savings_sen=result.savings_sen,
        categories=[CategorySpendOut(**vars(c)) for c in result.categories],
    )
