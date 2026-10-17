"""Category budgets (WP2): a monthly limit per spending category, its status for a month, and a
suggested set of limits worked out from the person's own income, bills, instalments and spending.

Category names travel in the body or the query string, never in the path (ADR D-43: "Drink/Dessert"
has a slash). "Spent" is the month summary's definition (ADR D-45), so a budget bar and the
spending-by-category panel can never disagree.
"""

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import WRITE_QUOTA, CurrentUser, DbDep
from app.api.schemas import NOT_FOUND_RESPONSE, PROTECTED_RESPONSES, ApiModel
from app.api.summary import MonthParam
from app.api.types import Sen, text
from app.core.errors import api_error

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


def _not_built():
    return api_error(501, "not_implemented", "This is not available yet.")


@router.get("", response_model=BudgetListOut)
def list_budgets(user: CurrentUser, db: DbDep) -> BudgetListOut:
    raise _not_built()


@router.put("", response_model=BudgetOut, dependencies=[WRITE_QUOTA])
def set_budget(body: BudgetIn, user: CurrentUser, db: DbDep) -> BudgetOut:
    raise _not_built()


@router.delete("", status_code=204, responses=NOT_FOUND_RESPONSE, dependencies=[WRITE_QUOTA])
def delete_budget(category: CategoryQuery, user: CurrentUser, db: DbDep) -> None:
    raise _not_built()


@router.get("/status", response_model=BudgetStatusOut)
def budget_status(month: MonthParam, user: CurrentUser, db: DbDep) -> BudgetStatusOut:
    raise _not_built()


@router.post("/suggest", response_model=BudgetSuggestionOut)
def suggest_budget(body: BudgetSuggestIn, user: CurrentUser, db: DbDep) -> BudgetSuggestionOut:
    raise _not_built()
