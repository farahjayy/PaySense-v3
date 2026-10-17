"""Category budgets (WP2): a monthly limit per spending category, its status for a month, and a
suggested set of limits worked out from the person's own income, bills, instalments and spending.

Category names travel in the body or the query string, never in the path (ADR D-43: "Drink/Dessert"
has a slash). "Spent" is the month summary's definition (ADR D-45), so a budget bar and the
spending-by-category panel can never disagree.
"""

import datetime as dt
from dataclasses import asdict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import WRITE_QUOTA, CurrentUser, DbDep, TodayDep
from app.api.schemas import NOT_FOUND_RESPONSE, PROTECTED_RESPONSES, ApiModel
from app.api.types import Sen, text
from app.core.errors import not_found, unprocessable
from app.db import budgets as budgets_repo
from app.db import plans as plans_repo
from app.db import recurring_items, transactions
from app.domain import budgets as domain

router = APIRouter(prefix="/budgets", tags=["budgets"], responses=PROTECTED_RESPONSES)

BudgetState = Literal["ok", "near", "over"]
CategoryQuery = Annotated[str, Query(min_length=1, max_length=60)]


class BudgetIn(BaseModel):
    """Set (create or replace) the monthly limit for one spending category."""

    model_config = ConfigDict(extra="forbid")

    category: text(60)
    limit_sen: Sen


class BudgetSuggestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: Annotated[str, Field(pattern=r"^(20\d{2}|2100)-(0[1-9]|1[0-2])$")] | None = Field(
        default=None, description="The month to plan for; defaults to the current month"
    )


class BudgetOut(ApiModel):
    category: str
    limit_sen: int
    updated_at: dt.datetime | None


class BudgetListOut(ApiModel):
    budgets: list[BudgetOut]


class BudgetStatusItemOut(ApiModel):
    category: str
    limit_sen: int
    spent_sen: int
    remaining_sen: int = Field(description="Limit less spent; negative when over")
    percent: float = Field(ge=0, description="Spent as a share of the limit (1.0 = 100%)")
    state: BudgetState
    projected_sen: int | None = Field(
        description="Spent so far scaled to the whole month; None for a past or future month"
    )
    projected_state: BudgetState | None


class BudgetStatusOut(ApiModel):
    month: str
    is_current: bool
    days_in_month: int
    days_elapsed: int
    items: list[BudgetStatusItemOut]
    total_limit_sen: int
    total_spent_sen: int
    refund_sen: int = Field(description="Refunds this month; taken off the month's spending")
    month_spend_sen: int = Field(description="The month summary's spending (gross less refunds)")
    unbudgeted_spend_sen: int = Field(
        description="Spending this month in categories with no budget"
    )
    near_at: float = Field(description="Share of the limit at which a budget is 'near'")
    over_at: float


class SuggestedBudgetOut(ApiModel):
    category: str
    share: float = Field(ge=0, le=1, description="This category's share of recent spending")
    recent_monthly_sen: int = Field(description="Average monthly spending in the months used")
    limit_sen: int


class BudgetSuggestionOut(ApiModel):
    """The arithmetic, shown so the person can see how the numbers were reached."""

    month: str
    income_sen: int
    income_basis: Literal["recurring", "average", "none"]
    bills_sen: int
    instalments_sen: int
    buffer_sen: int
    buffer_rate: float
    pool_sen: int = Field(
        description="Income less bills, instalments and the buffer; never below 0"
    )
    months_used: list[str]
    items: list[SuggestedBudgetOut]
    notes: list[str]


# ------------------------------------------------------------------ shared with the assistant
def _month_range(month: str) -> tuple[dt.date, dt.date]:
    first, last = domain._month_bounds(month)
    return first, last


def list_for(db: Any, user_id: str) -> BudgetListOut:
    return BudgetListOut(
        budgets=[BudgetOut.model_validate(r) for r in budgets_repo.list_budgets(db, user_id)]
    )


def status_for(db: Any, user_id: str, month: str, today: dt.date) -> BudgetStatusOut:
    first, last = _month_range(month)
    rows = transactions.list_for_breakdown(db, user_id, first, last)
    result = domain.budget_status(budgets_repo.list_budgets(db, user_id), rows, month, today)
    return BudgetStatusOut.model_validate(asdict(result))


def suggest_for(db: Any, user_id: str, month: str | None, today: dt.date) -> BudgetSuggestionOut:
    target = month or today.strftime("%Y-%m")
    result = domain.suggest_budget(
        recurring_items.list_items(db, user_id, active_only=True),
        plans_repo.list_with_instalments(db, user_id),
        transactions.list_for_forecast(db, user_id, today),
        target,
        today,
    )
    return BudgetSuggestionOut.model_validate(asdict(result))


def clean_category(raw: str) -> str:
    try:
        return domain.budget_category(raw)
    except ValueError as err:
        raise unprocessable("invalid_budget_category", str(err)) from err


def set_for(db: Any, user_id: str, body: BudgetIn) -> BudgetOut:
    """The one write path for a budget: the route and the assistant's confirm both use it."""
    row = budgets_repo.set_budget(db, user_id, clean_category(body.category), body.limit_sen)
    return BudgetOut.model_validate(row)


def delete_for(db: Any, user_id: str, category: str) -> None:
    if not budgets_repo.delete_budget(db, user_id, category.strip()):
        raise not_found("budget_not_found", "There is no budget for that category.")


# ------------------------------------------------------------------ routes
@router.get("", response_model=BudgetListOut)
def list_budgets(user: CurrentUser, db: DbDep) -> BudgetListOut:
    return list_for(db, user.id)


@router.put("", response_model=BudgetOut, dependencies=[WRITE_QUOTA])
def set_budget(body: BudgetIn, user: CurrentUser, db: DbDep) -> BudgetOut:
    """Create or replace the monthly limit for one spending category."""
    return set_for(db, user.id, body)


@router.delete("", status_code=204, responses=NOT_FOUND_RESPONSE, dependencies=[WRITE_QUOTA])
def delete_budget(category: CategoryQuery, user: CurrentUser, db: DbDep) -> Response:
    delete_for(db, user.id, category)
    return Response(status_code=204)


@router.get("/status", response_model=BudgetStatusOut)
def budget_status(
    user: CurrentUser,
    db: DbDep,
    today: TodayDep,
    month: Annotated[str | None, Query(pattern=r"^(20\d{2}|2100)-(0[1-9]|1[0-2])$")] = None,
) -> BudgetStatusOut:
    """Each budget against the month's spending (the month summary's definition, D-45). Without
    `month`, the current month in Malaysia (the server's clock, never the browser's)."""
    return status_for(db, user.id, month or today.strftime("%Y-%m"), today)


@router.post("/suggest", response_model=BudgetSuggestionOut)
def suggest_budget(
    body: BudgetSuggestIn, user: CurrentUser, db: DbDep, today: TodayDep
) -> BudgetSuggestionOut:
    """Suggested limits with the working shown. Stores nothing: saving one is a separate PUT."""
    return suggest_for(db, user.id, body.month, today)
