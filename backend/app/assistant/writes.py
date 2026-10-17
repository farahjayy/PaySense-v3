"""Tier 2: the writes (ADR D-48). NOT callable by the model and not in the tool registry.

Only the confirm endpoint runs these, after the person presses Confirm on a card built from the
stored, validated payload. Each one is the same shared function the screen's route uses, so a
write made through the assistant obeys every rule a write made on a screen does (ledger cap,
plan-create lock, duplicate window, the risk check re-run on the server).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.api import budgets as budgets_api
from app.api.assistant import BudgetDeleteIn
from app.api.budgets import BudgetIn
from app.api.imports import ConfirmIn, import_rows_for
from app.api.plans import PlanIn
from app.api.risk import confirm_for
from app.api.transactions import TransactionIn, create_for
from app.assistant.context import ToolContext
from app.core.errors import api_error


@dataclass(frozen=True)
class WriteFunction:
    name: str
    payload_model: type[BaseModel]
    run: Callable[[ToolContext, Any], dict[str, Any]]  # -> fields of ActionResultOut


def _add_transaction(ctx: ToolContext, body: TransactionIn) -> dict[str, Any]:
    out = create_for(ctx.db, ctx.user_id, body)
    return {"transaction": out, "message": "Transaction added."}


def _confirm_import(ctx: ToolContext, body: ConfirmIn) -> dict[str, Any]:
    out = import_rows_for(ctx.db, ctx.user_id, body)
    return {"imported": out, "message": f"{out.created} transaction(s) added."}


def _create_plan(ctx: ToolContext, body: PlanIn) -> dict[str, Any]:
    if ctx.predictor is None:
        raise api_error(503, "risk_check_unavailable", "The risk check is not available right now.")
    out = confirm_for(body, ctx.user_id, ctx.db, ctx.today, ctx.forecaster, ctx.predictor)
    return {"plan": out, "message": "Plan added and its risk report saved."}


def _set_budget(ctx: ToolContext, body: BudgetIn) -> dict[str, Any]:
    out = budgets_api.set_for(ctx.db, ctx.user_id, body)
    return {"budget": out, "message": f"{out.category} budget saved."}


def _delete_budget(ctx: ToolContext, body: BudgetDeleteIn) -> dict[str, Any]:
    budgets_api.delete_for(ctx.db, ctx.user_id, body.category)
    return {"message": f"{body.category} budget removed."}


WRITE_FUNCTIONS: dict[str, WriteFunction] = {
    w.name: w
    for w in (
        WriteFunction("add_transaction", TransactionIn, _add_transaction),
        WriteFunction("confirm_import", ConfirmIn, _confirm_import),
        WriteFunction("create_plan", PlanIn, _create_plan),
        WriteFunction("set_budget", BudgetIn, _set_budget),
        WriteFunction("delete_budget", BudgetDeleteIn, _delete_budget),
    )
}
