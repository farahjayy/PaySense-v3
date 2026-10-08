"""Per-user BNPL provider limits (ADR D-28). Keyed by (user_id, provider), so no ScopedTable —
but every statement still filters on `user_id`, which comes first and is validated."""

from datetime import UTC, datetime
from typing import Any

from app.db.base import require_user_id
from app.db.client import Database
from app.domain.providers import PROVIDER_KEYS

TABLE = "provider_limits"


def _check_provider(provider: object) -> str:
    if provider not in PROVIDER_KEYS:
        raise ValueError(f"provider must be one of {list(PROVIDER_KEYS)}")
    return str(provider)


def list_limits(db: Database, user_id: str) -> list[dict[str, Any]]:
    uid = require_user_id(user_id)
    return list(db.table(TABLE).select("*").eq("user_id", uid).execute().data)


def get_limit(db: Database, user_id: str, provider: str) -> int | None:
    uid = require_user_id(user_id)
    key = _check_provider(provider)
    rows = (
        db.table(TABLE).select("*").eq("user_id", uid).eq("provider", key).limit(1).execute().data
    )
    return rows[0]["limit_sen"] if rows else None


def upsert_limit(db: Database, user_id: str, provider: str, limit_sen: int) -> dict[str, Any]:
    uid = require_user_id(user_id)
    key = _check_provider(provider)
    if isinstance(limit_sen, bool) or not isinstance(limit_sen, int) or limit_sen <= 0:
        raise ValueError("limit_sen must be a positive whole number of sen")
    row = {
        "user_id": uid,
        "provider": key,
        "limit_sen": limit_sen,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    return db.table(TABLE).upsert(row, on_conflict="user_id,provider").execute().data[0]


def delete_limit(db: Database, user_id: str, provider: str) -> bool:
    uid = require_user_id(user_id)
    key = _check_provider(provider)
    deleted = db.table(TABLE).delete().eq("user_id", uid).eq("provider", key).execute().data
    return bool(deleted)
