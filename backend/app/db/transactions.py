"""Transactions repository. Every function takes `user_id` first and goes through ScopedTable,
so a user can only ever read or write their own rows (ADR D-03).

Validation happens here, in Python, before the database sees anything: a bad row should fail with
a clear message, not a constraint-violation code.
"""

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any

from app.db.base import ScopedTable, is_uuid
from app.db.client import Database
from app.domain.csv_import import fingerprint
from app.domain.flows import as_date

TABLE = "transactions"
TYPES = frozenset({"income", "expense", "savings"})
SOURCES = frozenset({"manual", "csv", "seed"})
CHUNK_SIZE = 500
UPDATABLE = frozenset(
    {"date", "amount_sen", "type", "category", "description", "account_name", "recurring_item_id"}
)


def _table(db: Database) -> ScopedTable:
    return ScopedTable(db, TABLE)


def _clean_date(value: dt.date | str) -> str:
    try:
        return as_date(value).isoformat()
    except (ValueError, TypeError) as err:
        raise ValueError(f"date must be a valid date, got {value!r}") from err


def _clean_amount(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("amount_sen must be a positive whole number of sen")
    return value


def _clean_text(value: object, field: str, *, required: bool) -> str | None:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        if required:
            raise ValueError(f"{field} is required")
        return None
    return text


def _clean_row(row: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    if row.get("type") not in TYPES:
        raise ValueError(f"type must be one of {sorted(TYPES)}")
    if source not in SOURCES:
        raise ValueError(f"source must be one of {sorted(SOURCES)}")
    return {
        "date": _clean_date(row["date"]),
        "amount_sen": _clean_amount(row.get("amount_sen")),
        "type": row["type"],
        "category": _clean_text(row.get("category"), "category", required=True),
        "description": _clean_text(row.get("description"), "description", required=False),
        "account_name": _clean_text(row.get("account_name"), "account_name", required=False),
        "is_bnpl": bool(row.get("is_bnpl", False)),
        "source": source,
        "bnpl_plan_id": row.get("bnpl_plan_id"),
        "bnpl_installment_id": row.get("bnpl_installment_id"),
        "recurring_item_id": row.get("recurring_item_id"),
    }


def create(
    db: Database,
    user_id: str,
    *,
    date: dt.date | str,
    amount_sen: int,
    type: str,  # noqa: A002 - mirrors the column name
    category: str,
    description: str | None = None,
    account_name: str | None = None,
    is_bnpl: bool = False,
    source: str = "manual",
    bnpl_plan_id: str | None = None,
    bnpl_installment_id: str | None = None,
    recurring_item_id: str | None = None,
) -> dict[str, Any]:
    row = _clean_row(
        {
            "date": date,
            "amount_sen": amount_sen,
            "type": type,
            "category": category,
            "description": description,
            "account_name": account_name,
            "is_bnpl": is_bnpl,
            "bnpl_plan_id": bnpl_plan_id,
            "bnpl_installment_id": bnpl_installment_id,
            "recurring_item_id": recurring_item_id,
        },
        source=source,
    )
    return _table(db).insert(user_id, row)


def bulk_create(
    db: Database, user_id: str, rows: Sequence[Mapping[str, Any]], *, source: str
) -> int:
    """Insert many rows (e.g. an import) in chunks. All rows are validated first; if a later chunk
    fails, the chunks already written are removed so a failed import leaves nothing behind."""
    cleaned = [_clean_row(row, source=source) for row in rows]
    table = _table(db)
    written: list[str] = []
    try:
        for start in range(0, len(cleaned), CHUNK_SIZE):
            created = table.insert_many(user_id, cleaned[start : start + CHUNK_SIZE])
            written.extend(row["id"] for row in created)
    except Exception:
        table.delete_many(user_id, written)
        raise
    return len(written)


def get(db: Database, user_id: str, transaction_id: str) -> dict[str, Any] | None:
    return _table(db).get(user_id, transaction_id)


def list_between(
    db: Database,
    user_id: str,
    start: dt.date,
    end: dt.date,
    *,
    type: str | None = None,  # noqa: A002
    category: str | None = None,
    newest_first: bool = True,
) -> list[dict[str, Any]]:
    filters = {k: v for k, v in (("type", type), ("category", category)) if v is not None}
    return _table(db).list_rows(
        user_id,
        order_by="date",
        descending=newest_first,
        between={"date": (start, end)},
        **filters,
    )


def update(
    db: Database, user_id: str, transaction_id: str, patch: Mapping[str, Any]
) -> dict[str, Any] | None:
    unknown = set(patch) - UPDATABLE
    if unknown:
        raise ValueError(f"{sorted(unknown)} cannot be updated")
    cleaned: dict[str, Any] = {}
    if "date" in patch:
        cleaned["date"] = _clean_date(patch["date"])
    if "amount_sen" in patch:
        cleaned["amount_sen"] = _clean_amount(patch["amount_sen"])
    if "type" in patch:
        if patch["type"] not in TYPES:
            raise ValueError(f"type must be one of {sorted(TYPES)}")
        cleaned["type"] = patch["type"]
    if "category" in patch:
        cleaned["category"] = _clean_text(patch["category"], "category", required=True)
    for field in ("description", "account_name"):
        if field in patch:
            cleaned[field] = _clean_text(patch[field], field, required=False)
    if "recurring_item_id" in patch:
        cleaned["recurring_item_id"] = patch["recurring_item_id"]
    if not cleaned:
        return _table(db).get(user_id, transaction_id)
    return _table(db).update(user_id, transaction_id, cleaned)


def delete(db: Database, user_id: str, transaction_id: str) -> bool:
    return _table(db).delete(user_id, transaction_id)


def fingerprints_between(db: Database, user_id: str, start: dt.date, end: dt.date) -> list[str]:
    """Duplicate-detection fingerprints of the stored rows in a date range (one per row, so
    multiplicity is preserved). Selects only the four columns a fingerprint needs."""
    rows = _table(db).list_rows(
        user_id, between={"date": (start, end)}, columns="date,amount_sen,type,description"
    )
    return [
        fingerprint(as_date(r["date"]), r["amount_sen"], r["type"], r.get("description"))
        for r in rows
    ]


def list_for_summary(db: Database, user_id: str) -> list[dict[str, Any]]:
    """Every transaction, reduced to the columns the month summary needs."""
    return _table(db).list_rows(user_id, order_by="date", columns="date,amount_sen,type,category")


def get_for_installment(db: Database, user_id: str, installment_id: str) -> dict[str, Any] | None:
    """The payment that settles this instalment, if one has been logged."""
    if not is_uuid(installment_id):
        return None
    rows = _table(db).list_rows(user_id, bnpl_installment_id=installment_id, limit=1)
    return rows[0] if rows else None


def list_for_plan(db: Database, user_id: str, plan_id: str) -> list[dict[str, Any]]:
    if not is_uuid(plan_id):
        return []
    return _table(db).list_rows(user_id, order_by="date", bnpl_plan_id=plan_id)


def delete_for_plan(db: Database, user_id: str, plan_id: str) -> int:
    ids = [row["id"] for row in list_for_plan(db, user_id, plan_id)]
    return _table(db).delete_many(user_id, ids)
