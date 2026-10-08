"""User-scoped table access — the isolation boundary (ADR D-03, hard constraint 4).

Every domain repository is built on `ScopedTable`. `user_id` is the first argument of every
method, is validated, and is added to every query (`eq("user_id", ...)`); inserted rows are
stamped with it, and callers cannot pass a different `user_id` in a row, patch or filter.
Route handlers never build queries; they call repository functions.
"""

from typing import Any

from app.db.client import Database

OWNER_COLUMN = "user_id"
ID_COLUMN = "id"


def require_user_id(user_id: object) -> str:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id is required for every user-scoped query")
    return user_id


class ScopedTable:
    def __init__(self, db: Database, table: str) -> None:
        self._db = db
        self._table = table

    def list(
        self,
        user_id: str,
        /,
        *,
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
        **equals: Any,
    ) -> list[dict[str, Any]]:
        uid = require_user_id(user_id)
        if OWNER_COLUMN in equals:
            raise ValueError(
                "user_id cannot be passed as a filter; it is always the first argument"
            )
        query = self._db.table(self._table).select("*").eq(OWNER_COLUMN, uid)
        for column, value in equals.items():
            query = query.eq(column, value)
        if order_by:
            query = query.order(order_by, desc=descending)
        if limit is not None:
            query = query.limit(limit)
        return list(query.execute().data)

    def get(self, user_id: str, row_id: str) -> dict[str, Any] | None:
        uid = require_user_id(user_id)
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
        deleted = (
            self._db.table(self._table)
            .delete()
            .eq(OWNER_COLUMN, uid)
            .eq(ID_COLUMN, row_id)
            .execute()
            .data
        )
        return bool(deleted)
