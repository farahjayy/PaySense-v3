"""Per-user settings. Keyed by user_id (one row per user), so it does not use ScopedTable."""

from typing import Any

from postgrest import APIError

from app.db.base import require_user_id
from app.db.client import Database

UNIQUE_VIOLATION = "23505"


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
