"""Monthly bills: every instalment due across all of the user's plans, grouped by month."""

import datetime as dt
from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep, TodayDep
from app.api.providers import ProviderKey
from app.api.schemas import PROTECTED_RESPONSES, ApiModel
from app.db import plans as plans_repo
from app.domain.bills import monthly_bills

router = APIRouter(prefix="/bills", tags=["bills"], responses=PROTECTED_RESPONSES)


class BillItemOut(ApiModel):
    plan_id: str
    item_name: str
    provider: ProviderKey
    provider_label: str
    seq: int
    amount_sen: int
    due_date: dt.date
    is_paid: bool


class BillMonthOut(ApiModel):
    month: str
    is_current: bool
    total_due_sen: int
    paid_total_sen: int
    fully_paid: bool
    has_overdue: bool
    items: list[BillItemOut]


class BillsOut(ApiModel):
    months: list[BillMonthOut]


@router.get("", response_model=BillsOut)
def bills(user: CurrentUser, db: DbDep, today: TodayDep) -> BillsOut:
    return bills_by_month_for(db, user.id, today)


def bills_by_month_for(db: Any, user_id: str, today: dt.date) -> BillsOut:
    """Shared by the route and the assistant's `get_bills_by_month` tool."""
    plans = plans_repo.list_with_instalments(db, user_id)
    return BillsOut.model_validate(monthly_bills(plans, today))
