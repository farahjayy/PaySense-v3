"""Recurring income and bills: CRUD, plus detected suggestions the user may confirm."""

import datetime as dt
from typing import Literal, Self

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.deps import CurrentUser, DbDep
from app.api.schemas import NOT_FOUND_RESPONSE, PROTECTED_RESPONSES, ApiModel
from app.api.types import AppDate, Sen, reject_explicit_nulls, text
from app.core.errors import not_found, unprocessable
from app.db import recurring_items as repo
from app.db import transactions
from app.engines.forecasting.recurring import detect

Kind = Literal["income", "bill"]
Cadence = Literal["weekly", "biweekly", "monthly", "semester", "custom"]

router = APIRouter(
    prefix="/recurring-items", tags=["recurring-items"], responses=PROTECTED_RESPONSES
)


class RecurringIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Kind
    name: text(80)
    amount_sen: Sen
    cadence: Cadence
    custom_interval_days: int | None = Field(default=None, ge=1, le=366)
    anchor_date: AppDate
    active: bool = True
    origin: Literal["manual", "detected"] = "manual"

    @model_validator(mode="after")
    def _custom_needs_an_interval(self) -> Self:
        if self.cadence == "custom" and self.custom_interval_days is None:
            raise ValueError("a custom cadence needs custom_interval_days")
        return self


class RecurringPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: text(80) | None = None
    amount_sen: Sen | None = None
    cadence: Cadence | None = None
    custom_interval_days: int | None = Field(default=None, ge=1, le=366)
    anchor_date: AppDate | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def _required_fields_cannot_be_null(self) -> Self:
        reject_explicit_nulls(self, ("name", "amount_sen", "cadence", "anchor_date", "active"))
        return self


class RecurringOut(ApiModel):
    id: str
    kind: Kind
    name: str
    amount_sen: int
    cadence: Cadence
    custom_interval_days: int | None
    anchor_date: dt.date
    active: bool
    origin: Literal["detected", "manual"]


class SuggestionOut(ApiModel):
    name: str
    display_name: str
    kind: Kind
    amount_sen: int
    cadence: Cadence
    anchor_date: dt.date
    confidence: float
    occurrences: int


def _missing():
    return not_found("recurring_item_not_found", "No such recurring item.")


@router.get("", response_model=list[RecurringOut])
def list_items(user: CurrentUser, db: DbDep, active_only: bool = False) -> list[RecurringOut]:
    return [
        RecurringOut.model_validate(row)
        for row in repo.list_items(db, user.id, active_only=active_only)
    ]


@router.get("/suggestions", response_model=list[SuggestionOut])
def suggestions(user: CurrentUser, db: DbDep) -> list[SuggestionOut]:
    """Patterns found in the user's own ledger. Nothing is saved: confirming one is a normal
    POST with `origin: "detected"`."""
    rows = transactions.list_for_forecast(db, user.id)
    known = [item["name"] for item in repo.list_items(db, user.id)]
    return [SuggestionOut.model_validate(vars(s)) for s in detect(rows, confirmed_names=known)]


@router.post("", response_model=RecurringOut, status_code=201)
def create_item(body: RecurringIn, user: CurrentUser, db: DbDep) -> RecurringOut:
    row = repo.create(db, user.id, **body.model_dump())
    return RecurringOut.model_validate(row)


@router.patch("/{item_id}", response_model=RecurringOut, responses=NOT_FOUND_RESPONSE)
def update_item(item_id: str, body: RecurringPatch, user: CurrentUser, db: DbDep) -> RecurringOut:
    patch = body.model_dump(exclude_unset=True)
    try:
        row = repo.update(db, user.id, item_id, patch)
    except ValueError as err:  # e.g. switching to "custom" without an interval
        raise unprocessable("validation_error", str(err)) from err
    if row is None:
        raise _missing()
    return RecurringOut.model_validate(row)


@router.delete("/{item_id}", status_code=204, responses=NOT_FOUND_RESPONSE)
def delete_item(item_id: str, user: CurrentUser, db: DbDep) -> Response:
    if not repo.delete(db, user.id, item_id):
        raise _missing()
    return Response(status_code=204)
