"""CSV import: preview (parses, writes nothing) -> the user edits -> confirm (re-validates, writes).

Stateless by design (ADR D-29): the server keeps nothing between the two calls, so a Render
restart cannot lose an upload and one user's preview can never be confirmed by another.
"""

import datetime as dt
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import CurrentUser, DbDep
from app.api.schemas import PROTECTED_RESPONSES, ApiModel
from app.api.types import AppDate, Sen, text
from app.core.errors import unprocessable
from app.db import transactions, user_settings
from app.domain.csv_import import MAX_ROWS, CsvImportError, flag_duplicates, parse_csv

logger = logging.getLogger("paysense")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
TxnType = Literal["income", "expense", "savings"]

router = APIRouter(prefix="/import", tags=["import"], responses=PROTECTED_RESPONSES)


class ImportRowOut(ApiModel):
    row: int
    date: dt.date
    amount_sen: int
    type: TxnType
    category_guess: str
    description: str | None
    issues: list[str]
    duplicate: bool


class SkippedRowOut(ApiModel):
    row: int
    reason: str


class ImportPreviewOut(ApiModel):
    rows: list[ImportRowOut]
    skipped: list[SkippedRowOut]
    duplicate_count: int


class ConfirmRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: AppDate
    amount_sen: Sen
    type: TxnType
    category: text(60)
    description: text(200, required=False) | None = None


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: Annotated[list[ConfirmRow], Field(min_length=1, max_length=MAX_ROWS)]


class ConfirmOut(ApiModel):
    created: int


@router.post("/csv", response_model=ImportPreviewOut)
def preview_csv(file: UploadFile, user: CurrentUser, db: DbDep) -> ImportPreviewOut:
    if not (file.filename or "").lower().endswith(".csv"):
        raise unprocessable("wrong_file_type", "Please upload a .csv file.")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise unprocessable("file_too_large", "File is over 5 MB. Export a shorter date range.")
    try:
        preview = parse_csv(data.decode("utf-8-sig", errors="replace"))
    except CsvImportError as err:
        raise unprocessable(err.code.lower(), err.message) from err

    first = min(r.date for r in preview.rows)
    last = max(r.date for r in preview.rows)
    stored = transactions.fingerprints_between(db, user.id, first, last)
    rows = flag_duplicates(preview.rows, stored)
    return ImportPreviewOut(
        rows=[
            ImportRowOut(
                row=r.row,
                date=r.date,
                amount_sen=r.amount_sen,
                type=r.type,  # type: ignore[arg-type]
                category_guess=r.category_guess,
                description=r.description,
                issues=list(r.issues),
                duplicate=r.duplicate,
            )
            for r in rows
        ],
        skipped=[SkippedRowOut(row=s.row, reason=s.reason) for s in preview.skipped],
        duplicate_count=sum(1 for r in rows if r.duplicate),
    )


@router.post("/confirm", response_model=ConfirmOut)
def confirm_import(body: ConfirmIn, user: CurrentUser, db: DbDep) -> ConfirmOut:
    created = transactions.bulk_create(
        db, user.id, [row.model_dump() for row in body.rows], source="csv"
    )
    try:
        user_settings.advance_onboarding_state(db, user.id, "history_imported")
    except Exception:
        # The rows are already saved; failing the request now would invite a duplicate retry.
        logger.exception("Could not record onboarding progress for user %s", user.id)
    return ConfirmOut(created=created)
