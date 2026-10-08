"""In-memory stand-in for the supabase-py client.

It implements the query-builder surface the repositories use (`table().select/insert/update/
delete` + `eq`, `ilike`, `gte`, `lte`, `in_`, `order`, `range`, `limit`, `execute`) so the *real*
repository code runs in unit tests. It also mimics the parts of the schema that matter for
isolation and consistency (migrations/0001_init.sql): unique constraints, composite
`(id, user_id)` foreign keys, `on delete cascade` / `set null`, all-or-nothing multi-row inserts,
and PostgREST's silent 1000-row cap. Violations raise `postgrest.APIError` with Postgres codes.
It does NOT enforce check constraints — repositories validate in Python first.
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

# table -> columns whose combined value must be unique (text is compared case-insensitively)
UNIQUE_KEYS: dict[str, list[tuple[str, ...]]] = {
    "users": [("username",)],
    "user_settings": [("user_id",)],
    "bnpl_installments": [("plan_id", "seq")],
    "provider_limits": [("user_id", "provider")],
}
# table -> defaults applied on insert (callables are invoked per row)
DEFAULTS: dict[str, dict[str, Any]] = {
    "users": {"persona": None},
    "user_settings": {"onboarding_state": "new"},
    "transactions": {
        "is_bnpl": False,
        "source": "manual",
        "description": None,
        "account_name": None,
        "bnpl_plan_id": None,
        "recurring_item_id": None,
    },
    "recurring_items": {"active": True, "custom_interval_days": None},
    "bnpl_plans": {
        "upfront_sen": 0,
        "schedule_source": "provider_rule",
        "monthly_fee_rate_pct": 0,
        "status": "active",
        "risk_score_at_creation": None,
        "risk_check_id": None,
        "risk_check_type": None,
    },
    "bnpl_installments": {"is_paid": False, "paid_date": None},
    "provider_limits": {"updated_at": lambda: _now()},
}
NO_ID_TABLES = {"user_settings", "provider_limits"}  # keyed by user_id; no `id`
HAS_CREATED_AT = {"users", "recurring_items", "risk_checks", "bnpl_plans", "transactions"}

# child table -> [(child column, parent table)]: composite (column, user_id) -> (id, user_id)
FOREIGN_KEYS: dict[str, list[tuple[str, str]]] = {
    "transactions": [("bnpl_plan_id", "bnpl_plans"), ("recurring_item_id", "recurring_items")],
    "bnpl_installments": [("plan_id", "bnpl_plans")],
    "bnpl_plans": [("risk_check_id", "risk_checks")],
}
# parent table -> [(child table, child column)]
ON_DELETE_SET_NULL: dict[str, list[tuple[str, str]]] = {
    "recurring_items": [("transactions", "recurring_item_id")],
    "bnpl_plans": [("transactions", "bnpl_plan_id")],
    "risk_checks": [("bnpl_plans", "risk_check_id")],
}
ON_DELETE_CASCADE: dict[str, list[tuple[str, str]]] = {
    "bnpl_plans": [("bnpl_installments", "plan_id")],
}


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


def _unique_key(row: dict[str, Any], cols: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(row[c].lower() if isinstance(row.get(c), str) else row.get(c) for c in cols)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> "FakeQuery":
        return FakeQuery(self, name)

    def rows(self, name: str) -> list[dict[str, Any]]:
        return self.tables.setdefault(name, [])

    def delete_rows(self, table: str, doomed: list[dict[str, Any]]) -> None:
        """Remove rows, then apply `on delete cascade` / `set null` to dependants."""
        ids = {id(r) for r in doomed}
        self.tables[table] = [r for r in self.rows(table) if id(r) not in ids]
        if table == "users":  # every user-owned table cascades from users
            for name in list(self.tables):
                gone = {r["id"] for r in doomed}
                keep = [r for r in self.rows(name) if r.get("user_id") not in gone]
                self.tables[name] = keep
        for child, column in ON_DELETE_SET_NULL.get(table, []):
            for row in self.rows(child):
                if any(
                    row.get(column) == d["id"] and row.get("user_id") == d["user_id"]
                    for d in doomed
                ):
                    row[column] = None
        for child, column in ON_DELETE_CASCADE.get(table, []):
            dependants = [
                row
                for row in self.rows(child)
                if any(
                    row.get(column) == d["id"] and row.get("user_id") == d["user_id"]
                    for d in doomed
                )
            ]
            if dependants:
                self.delete_rows(child, dependants)


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
        self._conflict: tuple[str, ...] = ()

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

    def upsert(self, payload: dict[str, Any], on_conflict: str = "") -> "FakeQuery":
        self._op, self._payload, self._conflict = "upsert", payload, tuple(on_conflict.split(","))
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

    def gte(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(lambda r: r.get(column) is not None and r[column] >= value)
        return self

    def lte(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(lambda r: r.get(column) is not None and r[column] <= value)
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeQuery":
        self._filters.append(lambda r: r.get(column) in values)
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
            "upsert": self._upsert,
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
        staged: list[dict[str, Any]] = []
        for raw in payload:  # like Postgres, a multi-row insert is all-or-nothing
            row = self._with_defaults(copy.deepcopy(raw))
            self._check_foreign_keys(row)
            self._check_unique(row, extra=staged)
            staged.append(row)
        self._db.rows(self._table).extend(staged)
        return staged

    def _update(self) -> list[dict[str, Any]]:
        rows = self._matching()
        patch = copy.deepcopy(self._payload)
        before = [dict(r) for r in rows]
        for row in rows:
            row.update(patch)
        try:
            for row in rows:
                self._check_foreign_keys(row)
                self._check_unique(row, ignore=row)
        except APIError:
            for row, original in zip(rows, before, strict=True):
                row.clear()
                row.update(original)
            raise
        return rows

    def _upsert(self) -> list[dict[str, Any]]:
        row = self._with_defaults(copy.deepcopy(self._payload))
        existing = next(
            (
                r
                for r in self._db.rows(self._table)
                if _unique_key(r, self._conflict) == _unique_key(row, self._conflict)
            ),
            None,
        )
        if existing is None:
            self._check_foreign_keys(row)
            self._check_unique(row)
            self._db.rows(self._table).append(row)
            return [row]
        existing.update({k: v for k, v in row.items() if k not in self._conflict})
        return [existing]

    def _delete(self) -> list[dict[str, Any]]:
        rows = self._matching()
        self._db.delete_rows(self._table, rows)
        return rows

    def _with_defaults(self, row: dict[str, Any]) -> dict[str, Any]:
        if self._table not in NO_ID_TABLES:
            row.setdefault("id", str(uuid.uuid4()))
        if self._table in HAS_CREATED_AT:
            row.setdefault("created_at", _now())
        for key, value in DEFAULTS.get(self._table, {}).items():
            row.setdefault(key, value() if callable(value) else value)
        return row

    def _check_foreign_keys(self, row: dict[str, Any]) -> None:
        owner_missing = self._table != "users" and "user_id" in row
        if owner_missing and not any(u["id"] == row["user_id"] for u in self._db.rows("users")):
            raise APIError({"message": "foreign key violation", "code": FOREIGN_KEY_VIOLATION})
        for column, parent in FOREIGN_KEYS.get(self._table, []):
            value = row.get(column)
            if value is None:
                continue  # MATCH SIMPLE: a null link is not checked
            if not any(
                p["id"] == value and p["user_id"] == row["user_id"] for p in self._db.rows(parent)
            ):
                raise APIError({"message": "foreign key violation", "code": FOREIGN_KEY_VIOLATION})

    def _check_unique(
        self,
        row: dict[str, Any],
        extra: list[dict[str, Any]] | None = None,
        ignore: dict[str, Any] | None = None,
    ) -> None:
        others = [r for r in self._db.rows(self._table) if r is not ignore] + (extra or [])
        for cols in UNIQUE_KEYS.get(self._table, []):
            if any(_unique_key(r, cols) == _unique_key(row, cols) for r in others):
                raise APIError({"message": "unique violation", "code": UNIQUE_VIOLATION})
