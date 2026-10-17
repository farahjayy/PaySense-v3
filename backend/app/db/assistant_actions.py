"""Pending assistant actions (ADR D-48). User-scoped through ScopedTable; a status change is an
update that only matches while the row still has the expected status, so it is atomic: two
confirms of one action cannot both succeed."""

import datetime as dt
from typing import Any

from app.db.base import ScopedTable
from app.db.client import Database

TABLE = "assistant_actions"
TYPES = frozenset(
    {"add_transaction", "confirm_import", "create_plan", "set_budget", "delete_budget"}
)
STATUSES = frozenset({"pending", "confirmed", "declined", "expired", "failed"})


def _table(db: Database) -> ScopedTable:
    return ScopedTable(db, TABLE)


def create(
    db: Database,
    user_id: str,
    *,
    type: str,  # noqa: A002 - mirrors the column
    payload: dict[str, Any],
    digest: str,
    summary: str,
    expires_at: dt.datetime,
    preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if type not in TYPES:
        raise ValueError(f"type must be one of {sorted(TYPES)}")
    return _table(db).insert(
        user_id,
        {
            "type": type,
            "payload": payload,
            "payload_digest": digest,
            "summary": summary[:500],
            "preview": preview,
            "expires_at": expires_at.isoformat(),
        },
    )


def get(db: Database, user_id: str, action_id: str) -> dict[str, Any] | None:
    return _table(db).get(user_id, action_id)


def find_pending(db: Database, user_id: str, type: str, digest: str) -> dict[str, Any] | None:  # noqa: A002
    rows = _table(db).list_rows(
        user_id, status="pending", type=type, payload_digest=digest, limit=1
    )
    return rows[0] if rows else None


def recent_confirmed(
    db: Database,
    user_id: str,
    type: str,
    digest: str,
    since: dt.datetime,  # noqa: A002
) -> bool:
    rows = _table(db).list_rows(
        user_id,
        status="confirmed",
        type=type,
        payload_digest=digest,
        between={"decided_at": (since.isoformat(), None)},
        limit=1,
    )
    return bool(rows)


def transition(
    db: Database,
    user_id: str,
    action_id: str,
    *,
    expected: str,
    to: str,
    result: dict[str, Any] | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any] | None:
    """Move an action from `expected` to `to`; None if it was not in `expected` any more."""
    if to not in STATUSES or expected not in STATUSES:
        raise ValueError("unknown status")
    patch: dict[str, Any] = {
        "status": to,
        "decided_at": (now or dt.datetime.now(dt.UTC)).isoformat(),
    }
    if result is not None:
        patch["result"] = result
    return _table(db).update(user_id, action_id, patch, where={"status": expected})


def list_actions(db: Database, user_id: str) -> list[dict[str, Any]]:
    return _table(db).list_rows(user_id, order_by="created_at")
