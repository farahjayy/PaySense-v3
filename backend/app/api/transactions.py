"""Transactions CRUD. Payments a BNPL plan logged belong to the plan and are read-only here."""

import base64
import datetime as dt
import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.deps import WRITE_QUOTA, CurrentUser, DbDep, TodayDep
from app.api.schemas import (
    CONFLICT_RESPONSE,
    NOT_FOUND_RESPONSE,
    PROTECTED_RESPONSES,
    ApiModel,
)
from app.api.types import MAX_DATE, MIN_DATE, AppDate, Sen, reject_explicit_nulls, text
from app.core.errors import api_error, not_found, unprocessable
from app.db import recurring_items, transactions
from app.db.base import is_uuid

TxnType = Literal["income", "expense", "savings"]
DEFAULT_WINDOW_DAYS = 90
MAX_PAGE = 500

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


class TransactionPageOut(ApiModel):
    transactions: list[TransactionOut]
    next_cursor: str | None = Field(description="Pass back as `cursor` for the next page")


def encode_cursor(row: dict[str, Any]) -> str:
    raw = json.dumps({"d": str(row["date"])[:10], "i": row["id"]}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str]:
    """(date, id) from a cursor; 422 for anything that is not one this API issued."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        day = dt.date.fromisoformat(data["d"]).isoformat()
        row_id = data["i"]
        if not isinstance(row_id, str) or not is_uuid(row_id):
            raise ValueError
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise unprocessable("invalid_cursor", "That page cursor is not valid.") from err
    return day, row_id


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


@router.get("", response_model=TransactionPageOut)
def list_transactions(
    user: CurrentUser,
    db: DbDep,
    today: TodayDep,
    start: Annotated[dt.date | None, Query(ge=MIN_DATE, le=MAX_DATE)] = None,
    end: Annotated[dt.date | None, Query(ge=MIN_DATE, le=MAX_DATE)] = None,
    kind: Annotated[TxnType | None, Query(alias="type")] = None,
    category: Annotated[str | None, Query(max_length=60)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = MAX_PAGE,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> TransactionPageOut:
    """Newest first, one page at a time (ADR D-49). Without `start`/`end`, the last 90 days up to
    today. Follow `next_cursor` until it is null."""
    last = end or today
    first = start or max(last - dt.timedelta(days=DEFAULT_WINDOW_DAYS), MIN_DATE)
    if first > last:
        raise unprocessable("invalid_range", "start must be on or before end.")
    after = decode_cursor(cursor) if cursor else None
    rows = transactions.list_page(
        db, user.id, first, last, after=after, limit=limit + 1, type=kind, category=category
    )
    page, more = rows[:limit], len(rows) > limit
    return TransactionPageOut(
        transactions=[TransactionOut.model_validate(row) for row in page],
        next_cursor=encode_cursor(page[-1]) if more else None,
    )


@router.post("", response_model=TransactionOut, status_code=201, dependencies=[WRITE_QUOTA])
def create_transaction(body: TransactionIn, user: CurrentUser, db: DbDep) -> TransactionOut:
    _require_own_recurring_item(db, user.id, body.recurring_item_id)
    row = transactions.create(db, user.id, **body.model_dump())
    return TransactionOut.model_validate(row)


@router.patch(
    "/{transaction_id}",
    response_model=TransactionOut,
    responses={**NOT_FOUND_RESPONSE, **CONFLICT_RESPONSE},
    dependencies=[WRITE_QUOTA],
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
    "/{transaction_id}",
    status_code=204,
    responses={**NOT_FOUND_RESPONSE, **CONFLICT_RESPONSE},
    dependencies=[WRITE_QUOTA],
)
def delete_transaction(transaction_id: str, user: CurrentUser, db: DbDep) -> Response:
    current = transactions.get(db, user.id, transaction_id)
    if current is None:
        raise _missing()
    if current["bnpl_plan_id"]:
        raise _managed_by_plan()
    transactions.delete(db, user.id, transaction_id)
    return Response(status_code=204)
