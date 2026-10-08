"""Month summary (income / spend / net per month) and how much history exists (ADR D-27)."""

import datetime as dt

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep, TodayDep
from app.api.schemas import PROTECTED_RESPONSES, ApiModel
from app.db.base import ScopedTable
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
    rows = ScopedTable(db, "transactions").list_rows(user.id, order_by="date")
    span = history_span(rows, today)
    return MonthSummaryOut(
        months=[MonthOut(**vars(m)) for m in month_summary(rows)],
        history=HistoryOut(**vars(span)) if span else None,
    )
