"""Per-user settings. Keyed by user_id (one row per user), so it does not use ScopedTable."""

from typing import Any

from postgrest import APIError

from app.db.base import require_user_id
from app.db.client import Database
from app.domain.money import MAX_AMOUNT_SEN

UNIQUE_VIOLATION = "23505"
ONBOARDING_STATES = ("new", "history_imported", "complete")


def get(db: Database, user_id: str) -> dict[str, Any] | None:
    uid = require_user_id(user_id)
    rows = db.table("user_settings").select("*").eq("user_id", uid).limit(1).execute().data
    return rows[0] if rows else None


def create_default(db: Database, user_id: str) -> dict[str, Any]:
    """Create the user's settings row with database defaults; return the existing one if present."""
    uid = require_user_id(user_id)
    existing = get(db, uid)
    if existing:
        return existing
    try:
        return db.table("user_settings").insert({"user_id": uid}).execute().data[0]
    except APIError as err:
        if err.code != UNIQUE_VIOLATION:
            raise
        return get(db, uid)  # lost a race with a concurrent create


def set_onboarding_state(db: Database, user_id: str, state: str) -> dict[str, Any]:
    """Record how far the user has got; creates the settings row if it is somehow missing."""
    uid = require_user_id(user_id)
    if state not in ONBOARDING_STATES:
        raise ValueError(f"onboarding_state must be one of {list(ONBOARDING_STATES)}")
    create_default(db, uid)
    updated = (
        db.table("user_settings")
        .update({"onboarding_state": state})
        .eq("user_id", uid)
        .execute()
        .data
    )
    return updated[0]


def advance_onboarding_state(db: Database, user_id: str, state: str) -> dict[str, Any]:
    """Move onboarding forward to `state`; never backwards (a later import must not send a
    finished user back to the start)."""
    uid = require_user_id(user_id)
    if state not in ONBOARDING_STATES:
        raise ValueError(f"onboarding_state must be one of {list(ONBOARDING_STATES)}")
    current = create_default(db, uid)
    if ONBOARDING_STATES.index(state) <= ONBOARDING_STATES.index(current["onboarding_state"]):
        return current
    return set_onboarding_state(db, uid, state)


def accept_consent(db: Database, user_id: str, version: str) -> dict[str, Any]:
    """Record that the user accepted this version of the privacy notice (WP19)."""
    import datetime as dt

    uid = require_user_id(user_id)
    create_default(db, uid)
    patch = {"consent_version": version, "consent_at": dt.datetime.now(dt.UTC).isoformat()}
    return db.table("user_settings").update(patch).eq("user_id", uid).execute().data[0]


def has_consented(db: Database, user_id: str, version: str) -> bool:
    row = get(db, user_id)
    return bool(row) and row.get("consent_version") == version


def get_savings_buffer(db: Database, user_id: str) -> int:
    """The savings the user recorded as a fall-back (ADR D-50), in sen; 0 when none."""
    row = get(db, user_id)
    return int((row or {}).get("savings_buffer_sen") or 0)


def set_savings_buffer(db: Database, user_id: str, savings_buffer_sen: int) -> dict[str, Any]:
    """Record the buffer (0 clears it); creates the settings row if it is somehow missing."""
    uid = require_user_id(user_id)
    value = savings_buffer_sen
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_AMOUNT_SEN:
        raise ValueError("savings_buffer_sen must be a whole number of sen, 0 or more")
    create_default(db, uid)
    return (
        db.table("user_settings")
        .update({"savings_buffer_sen": value})
        .eq("user_id", uid)
        .execute()
        .data[0]
    )
