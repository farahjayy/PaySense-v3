"""User-scoped table access — the isolation boundary (ADR D-03, hard constraint 4).

Every domain repository is built on `ScopedTable`. `user_id` is the first argument of every
method, is validated, and is added to every query (`eq("user_id", ...)`); inserted rows are
stamped with it, and callers cannot pass a different `user_id` in a row, patch or filter.
Route handlers never build queries; they call repository functions.

Never pass request-derived keyword arguments or an `order_by` straight from a client: column
names are not allow-listed here, so the caller (a repository function) must choose them.
Tables without an `id` primary key (`user_settings`, `provider_limits`) get their own module.
"""

import uuid
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from app.db.client import Database

OWNER_COLUMN = "user_id"
ID_COLUMN = "id"
# Supabase caps any single select at 1000 rows (PostgREST `max-rows`) without raising an error,
# so unbounded reads must page explicitly or they silently return a truncated ledger.
PAGE_SIZE = 1000


def require_user_id(user_id: object) -> str:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id is required for every user-scoped query")
    return user_id


def _wire(value: Any) -> Any:
    return value.isoformat() if isinstance(value, date) else value


def is_uuid(value: object) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return isinstance(value, str)


class ScopedTable:
    def __init__(self, db: Database, table: str) -> None:
        self._db = db
        self._table = table

    def _page_query(
        self,
        uid: str,
        equals: dict[str, Any],
        between: Mapping[str, tuple[Any, Any]] | None,
        order_by: str | None,
        descending: bool,
    ) -> Any:
        query = self._db.table(self._table).select("*").eq(OWNER_COLUMN, uid)
        for column, value in equals.items():
            query = query.eq(column, value)
        for column, (low, high) in (between or {}).items():
            if low is not None:
                query = query.gte(column, _wire(low))
            if high is not None:
                query = query.lte(column, _wire(high))
        if order_by:
            query = query.order(order_by, desc=descending)
        return query.order(ID_COLUMN)  # tie-break so pages never overlap or skip rows

    def list_rows(
        self,
        user_id: str,
        /,
        *,
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
        between: Mapping[str, tuple[Any, Any]] | None = None,
        **equals: Any,
    ) -> list[dict[str, Any]]:
        """All of the user's rows matching `equals` and the inclusive `between` ranges
        ({column: (low, high)}, either end may be None), paged internally past the 1000-row cap."""
        uid = require_user_id(user_id)
        if OWNER_COLUMN in equals:
            raise ValueError(
                "user_id cannot be passed as a filter; it is always the first argument"
            )
        if any(value is None for value in equals.values()):
            raise ValueError("filter values cannot be None")
        rows: list[dict[str, Any]] = []
        while limit is None or len(rows) < limit:
            start = len(rows)
            size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - start)
            page = (
                self._page_query(uid, equals, between, order_by, descending)
                .range(start, start + size - 1)
                .execute()
                .data
            )
            rows.extend(page)
            if len(page) < size:
                break
        return rows

    def get(self, user_id: str, row_id: str) -> dict[str, Any] | None:
        uid = require_user_id(user_id)
        if not is_uuid(row_id):
            return None
        rows = (
            self._db.table(self._table)
            .select("*")
            .eq(OWNER_COLUMN, uid)
            .eq(ID_COLUMN, row_id)
            .limit(1)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def insert(self, user_id: str, row: dict[str, Any]) -> dict[str, Any]:
        uid = require_user_id(user_id)
        if row.get(OWNER_COLUMN, uid) != uid:
            raise ValueError("row user_id does not match the user_id argument")
        created = self._db.table(self._table).insert({**row, OWNER_COLUMN: uid}).execute().data
        return created[0]

    def update(self, user_id: str, row_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        uid = require_user_id(user_id)
        if OWNER_COLUMN in patch or ID_COLUMN in patch:
            raise ValueError("user_id and id cannot be changed by an update")
        if not is_uuid(row_id):
            return None
        updated = (
            self._db.table(self._table)
            .update(dict(patch))
            .eq(OWNER_COLUMN, uid)
            .eq(ID_COLUMN, row_id)
            .execute()
            .data
        )
        return updated[0] if updated else None

    def delete(self, user_id: str, row_id: str) -> bool:
        uid = require_user_id(user_id)
        if not is_uuid(row_id):
            return False
        deleted = (
            self._db.table(self._table)
            .delete()
            .eq(OWNER_COLUMN, uid)
            .eq(ID_COLUMN, row_id)
            .execute()
            .data
        )
        return bool(deleted)

    def insert_many(self, user_id: str, rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """Insert rows in one request; every row is stamped with the caller's id. All rows are
        checked before anything is written."""
        uid = require_user_id(user_id)
        if any(row.get(OWNER_COLUMN, uid) != uid for row in rows):
            raise ValueError("row user_id does not match the user_id argument")
        if not rows:
            return []
        payload = [{**row, OWNER_COLUMN: uid} for row in rows]
        return list(self._db.table(self._table).insert(payload).execute().data)

    def delete_many(self, user_id: str, row_ids: Sequence[str]) -> int:
        """Delete the caller's rows with these ids; malformed or foreign ids are ignored."""
        uid = require_user_id(user_id)
        valid = [row_id for row_id in row_ids if is_uuid(row_id)]
        if not valid:
            return 0
        deleted = (
            self._db.table(self._table)
            .delete()
            .eq(OWNER_COLUMN, uid)
            .in_(ID_COLUMN, valid)
            .execute()
            .data
        )
        return len(deleted)
