"""Budgets repository (WP2). One row per user and category (case-insensitive); every function
takes `user_id` first and goes through ScopedTable (ADR D-03)."""

import datetime as dt
from typing import Any

from postgrest import APIError

from app.db.base import ScopedTable
from app.db.client import Database
from app.domain.money import MAX_AMOUNT_SEN

TABLE = "budgets"
UNIQUE_VIOLATION = "23505"


def _table(db: Database) -> ScopedTable:
    return ScopedTable(db, TABLE)


def _clean_limit(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= MAX_AMOUNT_SEN:
        raise ValueError("limit_sen must be a positive whole number of sen")
    return value


def list_budgets(db: Database, user_id: str) -> list[dict[str, Any]]:
    rows = _table(db).list_rows(user_id, order_by="category")
    return sorted(rows, key=lambda r: r["category"].casefold())


def find(db: Database, user_id: str, category: str) -> dict[str, Any] | None:
    """The user's budget for `category`, matched case-insensitively."""
    folded = category.casefold()
    return next((r for r in list_budgets(db, user_id) if r["category"].casefold() == folded), None)


def set_budget(db: Database, user_id: str, category: str, limit_sen: int) -> dict[str, Any]:
    """Create or replace the limit. `category` must already be a cleaned budget category."""
    limit = _clean_limit(limit_sen)
    now = dt.datetime.now(dt.UTC).isoformat()
    for _ in range(2):  # a concurrent create of the same budget: the second pass updates it
        existing = find(db, user_id, category)
        if existing is not None:
            patch = {"limit_sen": limit, "category": category, "updated_at": now}
            updated = _table(db).update(user_id, existing["id"], patch)
            if updated is not None:
                return updated
            continue
        try:
            return _table(db).insert(
                user_id, {"category": category, "limit_sen": limit, "updated_at": now}
            )
        except APIError as err:
            if err.code != UNIQUE_VIOLATION:
                raise
    raise RuntimeError("the budget changed while it was being saved")


def delete_budget(db: Database, user_id: str, category: str) -> bool:
    existing = find(db, user_id, category)
    return existing is not None and _table(db).delete(user_id, existing["id"])
