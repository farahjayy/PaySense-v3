"""Transactions CRUD. Payments a BNPL plan logged belong to the plan and are read-only here."""

import datetime as dt
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, model_validator

from app.api.deps import CurrentUser, DbDep, TodayDep
from app.api.schemas import (
    CONFLICT_RESPONSE,
    NOT_FOUND_RESPONSE,
    PROTECTED_RESPONSES,
    ApiModel,
)
from app.api.types import MAX_DATE, MIN_DATE, AppDate, Sen, reject_explicit_nulls, text
from app.core.errors import api_error, not_found, unprocessable
from app.db import recurring_items, transactions

TxnType = Literal["income", "expense", "savings"]
DEFAULT_WINDOW_DAYS = 90

router = APIRouter(prefix="/transactions", tags=["transactions"], responses=PROTECTED_RESPONSES)


class TransactionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: AppDate
    amount_sen: Sen
    type: TxnType
    category: text(60)
    description: text(200, required=False) | None = None
    account_name: text(80, required=False) | None = None
    recurring_item_id: str | None = None


class TransactionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: AppDate | None = None
    amount_sen: Sen | None = None
    type: TxnType | None = None
    category: text(60) | None = None
    description: text(200, required=False) | None = None
    account_name: text(80, required=False) | None = None
    recurring_item_id: str | None = None

    @model_validator(mode="after")
    def _required_fields_cannot_be_null(self):
        reject_explicit_nulls(self, ("date", "amount_sen", "type", "category"))
        return self


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
    start: Annotated[dt.date | None, Query(ge=MIN_DATE, le=MAX_DATE)] = None,
    end: Annotated[dt.date | None, Query(ge=MIN_DATE, le=MAX_DATE)] = None,
    kind: Annotated[TxnType | None, Query(alias="type")] = None,
    category: Annotated[str | None, Query(max_length=60)] = None,
) -> list[TransactionOut]:
    """Newest first. Without `start`/`end`, the last 90 days up to today."""
    last = end or today
    first = start or max(last - dt.timedelta(days=DEFAULT_WINDOW_DAYS), MIN_DATE)
    if first > last:
        raise unprocessable("invalid_range", "start must be on or before end.")
    rows = transactions.list_between(db, user.id, first, last, type=kind, category=category)
    return [TransactionOut.model_validate(row) for row in rows]


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(body: TransactionIn, user: CurrentUser, db: DbDep) -> TransactionOut:
    _require_own_recurring_item(db, user.id, body.recurring_item_id)
    row = transactions.create(db, user.id, **body.model_dump())
    return TransactionOut.model_validate(row)


@router.patch(
    "/{transaction_id}",
    response_model=TransactionOut,
    responses={**NOT_FOUND_RESPONSE, **CONFLICT_RESPONSE},
)
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


@router.delete(
    "/{transaction_id}", status_code=204, responses={**NOT_FOUND_RESPONSE, **CONFLICT_RESPONSE}
)
def delete_transaction(transaction_id: str, user: CurrentUser, db: DbDep) -> Response:
    current = transactions.get(db, user.id, transaction_id)
    if current is None:
        raise _missing()
    if current["bnpl_plan_id"]:
        raise _managed_by_plan()
    transactions.delete(db, user.id, transaction_id)
    return Response(status_code=204)
