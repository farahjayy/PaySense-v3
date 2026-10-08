"""In-memory stand-in for the supabase-py client.

It implements just the query-builder surface the repositories use (`table().select/insert/
update/delete` + `eq`, `ilike`, `order`, `limit`, `execute`) so the *real* repository code runs
in unit tests. Behaviour that matters for isolation is mimicked: unique constraints and
foreign keys raise `postgrest.APIError` with Postgres error codes, rows are copied in and out.
Integration tests (`-m integration`) are the check that this fake matches the real service.
"""

import copy
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from postgrest import APIError

MAX_ROWS = 1000  # Supabase/PostgREST default `max-rows`: larger selects are silently truncated
UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"

# table -> columns whose combined value must be unique (value is lower-cased for text)
UNIQUE_KEYS: dict[str, list[tuple[str, ...]]] = {
    "users": [("username",)],
    "user_settings": [("user_id",)],
}
# table -> defaults applied on insert (callables are invoked per row)
DEFAULTS: dict[str, dict[str, Any]] = {
    "users": {"persona": None},
    "user_settings": {
        "current_balance_sen": 0,
        "ledger_mode": True,
        "onboarding_state": "new",
        "balance_synced_at": lambda: _now(),
    },
}
NO_ID_TABLES = {"user_settings", "provider_limits"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]


def _like_to_regex(pattern: str) -> re.Pattern[str]:
    out, i = [], 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\" and i + 1 < len(pattern):
            out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        out.append(".*" if ch == "%" else "." if ch == "_" else re.escape(ch))
        i += 1
    return re.compile("^" + "".join(out) + "$", re.IGNORECASE | re.DOTALL)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> "FakeQuery":
        return FakeQuery(self, name)

    def rows(self, name: str) -> list[dict[str, Any]]:
        return self.tables.setdefault(name, [])


class FakeQuery:
    def __init__(self, db: FakeSupabase, table: str) -> None:
        self._db = db
        self._table = table
        self._op = "select"
        self._payload: Any = None
        self._filters: list[Any] = []
        self._orders: list[tuple[str, bool]] = []
        self._limit: int | None = None
        self._range: tuple[int, int] | None = None

    # -- operations
    def select(self, _columns: str = "*") -> "FakeQuery":
        self._op = "select"
        return self

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> "FakeQuery":
        self._op, self._payload = "insert", payload
        return self

    def update(self, patch: dict[str, Any]) -> "FakeQuery":
        self._op, self._payload = "update", patch
        return self

    def delete(self) -> "FakeQuery":
        self._op = "delete"
        return self

    # -- filters / modifiers
    def eq(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(lambda r: r.get(column) == value)
        return self

    def ilike(self, column: str, pattern: str) -> "FakeQuery":
        regex = _like_to_regex(pattern)
        self._filters.append(
            lambda r: isinstance(r.get(column), str) and bool(regex.match(r[column]))
        )
        return self

    def order(self, column: str, *, desc: bool = False) -> "FakeQuery":
        self._orders.append((column, desc))
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self._range = (start, end)
        return self

    def limit(self, n: int) -> "FakeQuery":
        self._limit = n
        return self

    # -- execution
    def _matching(self) -> list[dict[str, Any]]:
        return [r for r in self._db.rows(self._table) if all(f(r) for f in self._filters)]

    def execute(self) -> FakeResponse:
        run = {
            "select": self._select,
            "insert": self._insert,
            "update": self._update,
            "delete": self._delete,
        }[self._op]
        return FakeResponse(copy.deepcopy(run()))

    def _select(self) -> list[dict[str, Any]]:
        rows = self._matching()
        for column, desc in reversed(self._orders):  # stable sorts, last key first
            rows = sorted(rows, key=lambda r: (r.get(column) is None, r.get(column)), reverse=desc)
        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]
        if self._limit is not None:
            rows = rows[: self._limit]
        return rows[:MAX_ROWS]

    def _insert(self) -> list[dict[str, Any]]:
        payload = self._payload if isinstance(self._payload, list) else [self._payload]
        inserted = []
        for raw in payload:
            row = self._with_defaults(copy.deepcopy(raw))
            self._check_foreign_key(row)
            self._check_unique(row)
            self._db.rows(self._table).append(row)
            inserted.append(row)
        return inserted

    def _update(self) -> list[dict[str, Any]]:
        rows = self._matching()
        for row in rows:
            row.update(copy.deepcopy(self._payload))
        return rows

    def _delete(self) -> list[dict[str, Any]]:
        rows = self._matching()
        ids = {id(r) for r in rows}
        self._db.tables[self._table] = [r for r in self._db.rows(self._table) if id(r) not in ids]
        return rows

    def _with_defaults(self, row: dict[str, Any]) -> dict[str, Any]:
        if self._table not in NO_ID_TABLES:
            row.setdefault("id", str(uuid.uuid4()))
        row.setdefault("created_at", _now())
        for key, value in DEFAULTS.get(self._table, {}).items():
            row.setdefault(key, value() if callable(value) else value)
        return row

    def _check_foreign_key(self, row: dict[str, Any]) -> None:
        if self._table == "users" or "user_id" not in row:
            return
        if not any(u["id"] == row["user_id"] for u in self._db.rows("users")):
            raise APIError({"message": "foreign key violation", "code": FOREIGN_KEY_VIOLATION})

    def _check_unique(self, row: dict[str, Any]) -> None:
        def key(r: dict[str, Any], cols: tuple[str, ...]) -> tuple[Any, ...]:
            return tuple(r[c].lower() if isinstance(r.get(c), str) else r.get(c) for c in cols)

        for cols in UNIQUE_KEYS.get(self._table, []):
            if any(key(r, cols) == key(row, cols) for r in self._db.rows(self._table)):
                raise APIError({"message": "unique violation", "code": UNIQUE_VIOLATION})
