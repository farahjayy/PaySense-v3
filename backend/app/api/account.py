"""The person's own data (WP19, PDPA): the privacy notice, export, and delete.

Delete needs two confirmations: the typed phrase and the passphrase. It removes every row the
person owns in every table and keeps the account, so they can start again.
"""

import datetime as dt
import logging
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import WRITE_QUOTA, CurrentUser, DbDep, SettingsDep, rate_limited
from app.api.schemas import PROTECTED_RESPONSES, ApiModel, ErrorEnvelope
from app.core.errors import api_error, conflict
from app.core.passphrase import verify_passphrase
from app.db import account, user_settings, users
from app.domain.consent import CONSENT_VERSION, consent_sections

logger = logging.getLogger("paysense")
router = APIRouter(prefix="/account", tags=["account"], responses=PROTECTED_RESPONSES)
DELETE_PHRASE = "delete my data"


class ConsentSectionOut(ApiModel):
    title: str
    text: str


class ConsentOut(ApiModel):
    version: str
    accepted: bool
    accepted_at: dt.datetime | None
    sections: list[ConsentSectionOut]


class ConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=20)


class AccountExportOut(ApiModel):
    exported_at: dt.datetime
    user: dict[str, Any]
    settings: dict[str, Any] | None
    tables: dict[str, list[dict[str, Any]]]


class DeleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["delete my data"] = Field(description='Type exactly "delete my data"')
    passphrase: str = Field(min_length=1, max_length=128)


class DeleteOut(ApiModel):
    deleted: dict[str, int]
    message: str


def consent_for(db: Any, user_id: str, provider: str) -> ConsentOut:
    row = user_settings.get(db, user_id) or {}
    accepted = row.get("consent_version") == CONSENT_VERSION
    return ConsentOut(
        version=CONSENT_VERSION,
        accepted=accepted,
        accepted_at=row.get("consent_at") if accepted else None,
        sections=[ConsentSectionOut(title=t, text=x) for t, x in consent_sections(provider)],
    )


@router.get("/consent", response_model=ConsentOut)
def get_consent(user: CurrentUser, db: DbDep, settings: SettingsDep) -> ConsentOut:
    """The current privacy and assistant notice, and whether this person has accepted it."""
    return consent_for(db, user.id, settings.llm_provider)


@router.post(
    "/consent",
    response_model=ConsentOut,
    dependencies=[WRITE_QUOTA],
    responses={409: {"model": ErrorEnvelope, "description": "Not the current version"}},
)
def accept_consent(
    body: ConsentIn, user: CurrentUser, db: DbDep, settings: SettingsDep
) -> ConsentOut:
    if body.version != CONSENT_VERSION:
        raise conflict("consent_outdated", "The notice has changed. Read the new one first.")
    user_settings.accept_consent(db, user.id, CONSENT_VERSION)
    return consent_for(db, user.id, settings.llm_provider)


@router.post(
    "/export", response_model=AccountExportOut, dependencies=[rate_limited("export", 5, 3600)]
)
def export_data(user: CurrentUser, db: DbDep) -> AccountExportOut:
    """Everything PaySense holds about you, as JSON (no passphrase hash)."""
    data = account.export(db, user.id)
    return AccountExportOut(exported_at=dt.datetime.now(dt.UTC), **data)


@router.post(
    "/delete",
    response_model=DeleteOut,
    dependencies=[WRITE_QUOTA, rate_limited("account-delete", 3, 3600)],
    responses={403: {"model": ErrorEnvelope, "description": "Wrong passphrase"}},
)
def delete_data(body: DeleteIn, user: CurrentUser, db: DbDep) -> DeleteOut:
    """Delete every row you own in every table. Your account stays, empty."""
    row = users.get_by_id(db, user.id) or {}
    if not verify_passphrase(row.get("passphrase_hash"), body.passphrase):
        raise api_error(
            403, "wrong_passphrase", "That passphrase is not right. Nothing was deleted."
        )
    counts = account.delete_everything(db, user.id)
    logger.info("account data deleted: %s rows", sum(counts.values()))  # no ids, no content
    return DeleteOut(deleted=counts, message="Your data has been deleted.")
