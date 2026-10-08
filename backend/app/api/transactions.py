"""Transactions CRUD. Payments a BNPL plan logged belong to the plan and are read-only here."""

import datetime as dt
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import CurrentUser, DbDep, TodayDep
from app.api.schemas import NOT_FOUND_RESPONSE, PROTECTED_RESPONSES, ApiModel
from app.api.types import Sen
from app.core.errors import api_error, not_found, unprocessable
from app.db import recurring_items, transactions

TxnType = Literal["income", "expense", "savings"]
DEFAULT_WINDOW_DAYS = 90

router = APIRouter(prefix="/transactions", tags=["transactions"], responses=PROTECTED_RESPONSES)


class TransactionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: dt.date
    amount_sen: Sen
    type: TxnType
    category: str = Field(min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=200)
    account_name: str | None = Field(default=None, max_length=80)
    recurring_item_id: str | None = None


class TransactionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: dt.date | None = None
    amount_sen: Sen | None = None
    type: TxnType | None = None
    category: str | None = Field(default=None, min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=200)
    account_name: str | None = Field(default=None, max_length=80)
    recurring_item_id: str | None = None


class TransactionOut(ApiModel):
    id: str
    date: dt.date
    amount_sen: int
    type: TxnType
    category: str
    description: str | None
    account_name: str | None
    is_bnpl: bool
    source: Literal["manual", "csv", "seed"]
    bnpl_plan_id: str | None
    recurring_item_id: str | None


def _missing():
    return not_found("transaction_not_found", "No such transaction.")


def _managed_by_plan():
    return api_error(
        409,
        "managed_by_plan",
        "This payment was logged by a BNPL plan. Change or delete the plan instead.",
    )


def _require_own_recurring_item(db: Any, user_id: str, item_id: str | None) -> None:
    if item_id is not None and recurring_items.get(db, user_id, item_id) is None:
        raise unprocessable("recurring_item_not_found", "No such recurring item.")


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    user: CurrentUser,
    db: DbDep,
    today: TodayDep,
    start: dt.date | None = None,
    end: dt.date | None = None,
    kind: Annotated[TxnType | None, Query(alias="type")] = None,
    category: Annotated[str | None, Query(max_length=60)] = None,
) -> list[TransactionOut]:
    """Newest first. Without `start`/`end`, the last 90 days up to today."""
    last = end or today
    first = start or last - dt.timedelta(days=DEFAULT_WINDOW_DAYS)
    if first > last:
        raise unprocessable("invalid_range", "start must be on or before end.")
    rows = transactions.list_between(db, user.id, first, last, type=kind, category=category)
    return [TransactionOut.model_validate(row) for row in rows]


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(body: TransactionIn, user: CurrentUser, db: DbDep) -> TransactionOut:
    _require_own_recurring_item(db, user.id, body.recurring_item_id)
    row = transactions.create(db, user.id, **body.model_dump())
    return TransactionOut.model_validate(row)


@router.patch("/{transaction_id}", response_model=TransactionOut, responses=NOT_FOUND_RESPONSE)
def update_transaction(
    transaction_id: str, body: TransactionPatch, user: CurrentUser, db: DbDep
) -> TransactionOut:
    current = transactions.get(db, user.id, transaction_id)
    if current is None:
        raise _missing()
    if current["bnpl_plan_id"]:
        raise _managed_by_plan()
    patch = body.model_dump(exclude_unset=True)
    _require_own_recurring_item(db, user.id, patch.get("recurring_item_id"))
    updated = transactions.update(db, user.id, transaction_id, patch) if patch else current
    if updated is None:
        raise _missing()
    return TransactionOut.model_validate(updated)


@router.delete("/{transaction_id}", status_code=204, responses=NOT_FOUND_RESPONSE)
def delete_transaction(transaction_id: str, user: CurrentUser, db: DbDep) -> Response:
    current = transactions.get(db, user.id, transaction_id)
    if current is None:
        raise _missing()
    if current["bnpl_plan_id"]:
        raise _managed_by_plan()
    transactions.delete(db, user.id, transaction_id)
    return Response(status_code=204)
