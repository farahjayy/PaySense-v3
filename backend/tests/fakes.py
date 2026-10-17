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
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from postgrest import APIError

MAX_IN_VALUES = 150  # stands in for the gateway URL-length limit on `id=in.(...)`
MAX_ROWS = 1000  # Supabase/PostgREST default `max-rows`: larger selects are silently truncated
UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"

# table -> columns whose combined value must be unique (text is compared case-insensitively)
UNIQUE_KEYS: dict[str, list[tuple[str, ...]]] = {
    "users": [("username",)],
    "user_settings": [("user_id",)],
    "bnpl_installments": [("plan_id", "seq")],
    "provider_limits": [("user_id", "provider")],
    "user_categories": [("user_id", "name")],
    "transactions": [("bnpl_installment_id",)],  # partial unique index: NULLs never collide
    "user_locks": [("user_id", "name")],
    "budgets": [("user_id", "category")],
}
# table -> defaults applied on insert (callables are invoked per row)
DEFAULTS: dict[str, dict[str, Any]] = {
    "users": {"persona": None, "passphrase_hash": None, "token_version": 0},
    "user_settings": {
        "onboarding_state": "new",
        "savings_buffer_sen": 0,
        "consent_version": None,
        "consent_at": None,
    },
    "transactions": {
        "is_bnpl": False,
        "source": "manual",
        "description": None,
        "account_name": None,
        "bnpl_plan_id": None,
        "bnpl_installment_id": None,
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
    "assistant_actions": {"status": "pending", "preview": None, "result": None, "decided_at": None},
    "assistant_events": {
        "tier": None,
        "tool": None,
        "status": None,
        "action_id": None,
        "provider": None,
        "model": None,
        "input_tokens": None,
        "output_tokens": None,
        "detail": None,
    },
}
NO_ID_TABLES = {"user_settings", "provider_limits", "user_locks"}  # keyed by user_id; no `id`
HAS_CREATED_AT = {
    "users",
    "recurring_items",
    "risk_checks",
    "bnpl_plans",
    "transactions",
    "user_categories",
    "budgets",
    "assistant_actions",
    "assistant_events",
}

# child table -> [(child column, parent table)]: composite (column, user_id) -> (id, user_id)
FOREIGN_KEYS: dict[str, list[tuple[str, str]]] = {
    "transactions": [
        ("bnpl_plan_id", "bnpl_plans"),
        ("bnpl_installment_id", "bnpl_installments"),
        ("recurring_item_id", "recurring_items"),
    ],
    "bnpl_installments": [("plan_id", "bnpl_plans")],
    "bnpl_plans": [("risk_check_id", "risk_checks")],
    "assistant_events": [("action_id", "assistant_actions")],
}
# parent table -> [(child table, child column)]
ON_DELETE_SET_NULL: dict[str, list[tuple[str, str]]] = {
    "recurring_items": [("transactions", "recurring_item_id")],
    "bnpl_plans": [("transactions", "bnpl_plan_id")],
    "risk_checks": [("bnpl_plans", "risk_check_id")],
    "assistant_actions": [("assistant_events", "action_id")],
    "bnpl_installments": [("transactions", "bnpl_installment_id")],
}
ON_DELETE_CASCADE: dict[str, list[tuple[str, str]]] = {
    "bnpl_plans": [("bnpl_installments", "plan_id")],
}


# Every test account's passphrase. Hashed once per run: scrypt is deliberately slow.
TEST_PASSPHRASE = "correct horse battery staple"
_TEST_HASH: list[str] = []


def give_test_passphrase(db: "FakeSupabase", username: str) -> None:
    """Set TEST_PASSPHRASE on a seeded fake user without paying for scrypt every time."""
    from app.core.passphrase import hash_passphrase

    if not _TEST_HASH:
        _TEST_HASH.append(hash_passphrase(TEST_PASSPHRASE))
    for row in db.rows("users"):
        if row["username"].lower() == username.lower():
            row["passphrase_hash"] = _TEST_HASH[0]


def accept_test_consent(db: "FakeSupabase", username: str) -> None:
    """Mark a seeded fake user as having accepted the current privacy notice (WP19)."""
    from app.domain.consent import CONSENT_VERSION

    user = next(u for u in db.rows("users") if u["username"].lower() == username.lower())
    for row in db.rows("user_settings"):
        if row["user_id"] == user["id"]:
            row["consent_version"] = CONSENT_VERSION
            row["consent_at"] = _now()


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]
    count: int | None = None


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
        self._injected: list[tuple[str, str, Exception]] = []

    def fail_after_commit(self, table: str, op: str, error: Exception) -> None:
        """Make the next `op` on `table` APPLY and then raise: the "committed, but the client saw
        a timeout" outcome that no unit test of a plain failure can reproduce."""
        self._injected.append((table, op, error))

    def raise_if_injected(self, table: str, op: str) -> None:
        for index, (t, o, error) in enumerate(self._injected):
            if (t, o) == (table, op):
                del self._injected[index]
                raise error

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
        self._columns: list[str] | None = None
        self._count: str | None = None
        self._head = False

    # -- operations
    def select(
        self, columns: str = "*", count: str | None = None, head: bool = False
    ) -> "FakeQuery":
        self._op = "select"
        self._columns = None if columns.strip() == "*" else [c.strip() for c in columns.split(",")]
        self._count, self._head = count, head
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

    def lt(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(lambda r: r.get(column) is not None and r[column] < value)
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeQuery":
        if len(values) > MAX_IN_VALUES:  # PostgREST puts these in the URL; gateways cap its length
            raise RuntimeError(f"request URI too long: {len(values)} values in one in() filter")
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
        if self._op in ("insert", "update", "upsert"):
            json.dumps(self._payload)  # httpx would fail on a date/Decimal the fake would accept
        if self._op == "select" and self._count:
            total = len(self._matching())  # PostgREST counts every match, ignoring the row cap
            result = [] if self._head else copy.deepcopy(run())
            return FakeResponse(result, count=total)
        result = copy.deepcopy(run())
        self._db.raise_if_injected(self._table, self._op)
        return FakeResponse(result)

    def _select(self) -> list[dict[str, Any]]:
        rows = self._matching()
        for column, desc in reversed(self._orders):  # stable sorts, last key first
            rows = sorted(rows, key=lambda r: (r.get(column) is None, r.get(column)), reverse=desc)
        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]
        if self._limit is not None:
            rows = rows[: self._limit]
        rows = rows[:MAX_ROWS]
        if self._columns is not None:  # like PostgREST: only the asked-for columns come back
            rows = [{c: r[c] for c in self._columns if c in r} for r in rows]
        return rows

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
            if any(row.get(c) is None for c in cols):
                continue  # in SQL, a NULL never collides with another NULL
            if any(_unique_key(r, cols) == _unique_key(row, cols) for r in others):
                raise APIError({"message": "unique violation", "code": UNIQUE_VIOLATION})
