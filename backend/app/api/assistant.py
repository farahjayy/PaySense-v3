"""The assistant (WP4, ADRs D-47, D-48, D-53): chat, guided tool runs, and confirming the writes it
proposes.

The model only reads (Tier 0) and computes or proposes (Tier 1). A write (Tier 2) runs only here,
in `confirm`, after the person presses a button on a card built from the validated payload.
"""

import datetime as dt
from typing import Annotated, Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.bills import BillsOut
from app.api.budgets import BudgetIn, BudgetListOut, BudgetOut, BudgetStatusOut, BudgetSuggestionOut
from app.api.deps import WRITE_QUOTA, CurrentUser, DbDep
from app.api.forecast import ForecastOut
from app.api.imports import ConfirmIn, ConfirmOut
from app.api.insights import BillAnalysisOut, SpendingInsightsOut
from app.api.plans import PlanIn, PlanOut, PlanPreviewOut
from app.api.provider_limits import LimitOut
from app.api.providers import ProviderOut
from app.api.recommendations import RecommendationListOut
from app.api.risk import RiskCheckOut, RiskConfirmOut
from app.api.schemas import NOT_FOUND_RESPONSE, PROTECTED_RESPONSES, ApiModel, ErrorEnvelope
from app.api.summary import CategorySummaryOut, MonthSummaryOut
from app.api.transactions import TransactionIn, TransactionOut
from app.api.types import text
from app.core.errors import api_error

router = APIRouter(prefix="/assistant", tags=["assistant"], responses=PROTECTED_RESPONSES)

MAX_MESSAGE_CHARS = 8000  # a pasted statement (WP4d) fits; anything longer is refused
MAX_HISTORY_TURNS = 12
Tier = Literal[0, 1, 2]
Mode = Literal["llm", "guided"]
ActionType = Literal[
    "add_transaction", "confirm_import", "create_plan", "set_budget", "delete_budget"
]
ActionStatus = Literal["pending", "confirmed", "declined", "expired", "failed"]
ASSISTANT_RESPONSES: dict[int | str, dict[str, Any]] = {
    429: {"model": ErrorEnvelope, "description": "Too many requests, or the daily budget is used"},
    503: {"model": ErrorEnvelope, "description": "The assistant is switched off"},
}


# ------------------------------------------------------------------ requests
class ChatTurnIn(BaseModel):
    """Earlier turns, as plain text only. Tool results are never accepted from the client: they
    are always recomputed on the server, so forged history cannot inject a result."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    text: text(4000)


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: text(MAX_MESSAGE_CHARS)
    history: Annotated[list[ChatTurnIn], Field(max_length=MAX_HISTORY_TURNS)] = []


class RunToolIn(BaseModel):
    """Guided mode: run one Tier 0 or Tier 1 tool directly (a button or a small form)."""

    model_config = ConfigDict(extra="forbid")

    tool: Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[a-z_]+$")]
    arguments: dict[str, Any] = {}


class BudgetDeleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: text(60)


# ------------------------------------------------------------------ cards (tool results)
class ProvidersCardOut(ApiModel):
    providers: list[ProviderOut]
    limits: list[LimitOut]


class TransactionListOut(ApiModel):
    transactions: list[TransactionOut]
    limit: int
    descriptions_redacted: bool


class PlanListOut(ApiModel):
    plans: list[PlanOut]


class PastedRowOut(ApiModel):
    date: dt.date
    amount_sen: int
    type: Literal["income", "expense", "savings"]
    category: str
    description: str | None
    duplicate: bool


class RejectedRowOut(ApiModel):
    index: int
    reason: str


class PastePreviewOut(ApiModel):
    rows: list[PastedRowOut]
    rejected: list[RejectedRowOut]
    duplicate_count: int


class _Card(ApiModel):
    title: str


class RiskCard(_Card):
    kind: Literal["risk"]
    data: RiskCheckOut


class ForecastCard(_Card):
    kind: Literal["forecast"]
    data: ForecastOut


class MonthSummaryCard(_Card):
    kind: Literal["month_summary"]
    data: MonthSummaryOut


class CategorySpendingCard(_Card):
    kind: Literal["category_spending"]
    data: CategorySummaryOut


class TransactionsCard(_Card):
    kind: Literal["transactions"]
    data: TransactionListOut


class BillsCard(_Card):
    kind: Literal["bills"]
    data: BillsOut


class BillAnalysisCard(_Card):
    kind: Literal["bill_analysis"]
    data: BillAnalysisOut


class SpendingInsightsCard(_Card):
    kind: Literal["spending_insights"]
    data: SpendingInsightsOut


class PlansCard(_Card):
    kind: Literal["plans"]
    data: PlanListOut


class PlanPreviewCard(_Card):
    kind: Literal["plan_preview"]
    data: PlanPreviewOut


class ProvidersCard(_Card):
    kind: Literal["providers"]
    data: ProvidersCardOut


class BudgetsCard(_Card):
    kind: Literal["budgets"]
    data: BudgetListOut


class BudgetStatusCard(_Card):
    kind: Literal["budget_status"]
    data: BudgetStatusOut


class BudgetSuggestionCard(_Card):
    kind: Literal["budget_suggestion"]
    data: BudgetSuggestionOut


class RecommendationsCard(_Card):
    kind: Literal["recommendations", "alerts"]
    data: RecommendationListOut


class PastePreviewCard(_Card):
    kind: Literal["paste_preview"]
    data: PastePreviewOut


Card = Annotated[
    RiskCard
    | ForecastCard
    | MonthSummaryCard
    | CategorySpendingCard
    | TransactionsCard
    | BillsCard
    | BillAnalysisCard
    | SpendingInsightsCard
    | PlansCard
    | PlanPreviewCard
    | ProvidersCard
    | BudgetsCard
    | BudgetStatusCard
    | BudgetSuggestionCard
    | RecommendationsCard
    | PastePreviewCard,
    Field(discriminator="kind"),
]


# ------------------------------------------------------------------ pending actions
class _Action(ApiModel):
    id: str
    status: ActionStatus
    summary: str = Field(description="Built by the server from the validated payload")
    expires_at: dt.datetime


class AddTransactionAction(_Action):
    type: Literal["add_transaction"]
    payload: TransactionIn


class ConfirmImportAction(_Action):
    type: Literal["confirm_import"]
    payload: ConfirmIn


class CreatePlanAction(_Action):
    type: Literal["create_plan"]
    payload: PlanIn
    preview: PlanPreviewOut | None = None


class SetBudgetAction(_Action):
    type: Literal["set_budget"]
    payload: BudgetIn


class DeleteBudgetAction(_Action):
    type: Literal["delete_budget"]
    payload: BudgetDeleteIn


PendingActionOut = Annotated[
    AddTransactionAction
    | ConfirmImportAction
    | CreatePlanAction
    | SetBudgetAction
    | DeleteBudgetAction,
    Field(discriminator="type"),
]


class StepOut(ApiModel):
    tool: str
    tier: Tier
    status: Literal["ok", "refused", "error"]
    inputs: dict[str, Any]
    summary: str


class ChatOut(ApiModel):
    reply: str
    mode: Mode
    provider: str | None
    model: str | None
    steps: list[StepOut]
    cards: list[Card]
    pending_actions: list[PendingActionOut]
    narration_replaced: bool = Field(
        description="True when the model's wording failed the number check and a template was used"
    )
    refused: bool = Field(description="True when the request was out of scope")


class AssistantStatusOut(ApiModel):
    mode: Mode
    provider: str | None
    model: str | None
    reason: str | None = Field(description="Why guided mode, when it is")
    tokens_used_today: int
    daily_token_budget: int


class ActionResultOut(ApiModel):
    id: str
    type: ActionType
    status: ActionStatus
    transaction: TransactionOut | None = None
    imported: ConfirmOut | None = None
    plan: RiskConfirmOut | None = None
    budget: BudgetOut | None = None
    message: str


def _not_built():
    return api_error(501, "not_implemented", "This is not available yet.")


# ------------------------------------------------------------------ routes
@router.get("/status", response_model=AssistantStatusOut)
def status(user: CurrentUser, db: DbDep) -> AssistantStatusOut:
    raise _not_built()


@router.get("/opening", response_model=ChatOut, responses=ASSISTANT_RESPONSES)
def opening(user: CurrentUser, db: DbDep) -> ChatOut:
    """The first turn: what needs attention now (the alerts), with no model call."""
    raise _not_built()


@router.post("/chat", response_model=ChatOut, responses=ASSISTANT_RESPONSES)
def chat(body: ChatIn, user: CurrentUser, db: DbDep) -> ChatOut:
    raise _not_built()


@router.post("/run", response_model=ChatOut, responses=ASSISTANT_RESPONSES)
def run_tool(body: RunToolIn, user: CurrentUser, db: DbDep) -> ChatOut:
    raise _not_built()


@router.get("/actions/{action_id}", response_model=PendingActionOut, responses=NOT_FOUND_RESPONSE)
def get_action(action_id: str, user: CurrentUser, db: DbDep) -> Any:
    raise _not_built()


@router.post(
    "/actions/{action_id}/confirm",
    response_model=ActionResultOut,
    responses={**NOT_FOUND_RESPONSE, **ASSISTANT_RESPONSES},
    dependencies=[WRITE_QUOTA],
)
def confirm_action(action_id: str, user: CurrentUser, db: DbDep) -> ActionResultOut:
    raise _not_built()


@router.post(
    "/actions/{action_id}/decline", response_model=ActionResultOut, responses=NOT_FOUND_RESPONSE
)
def decline_action(action_id: str, user: CurrentUser, db: DbDep) -> ActionResultOut:
    raise _not_built()
