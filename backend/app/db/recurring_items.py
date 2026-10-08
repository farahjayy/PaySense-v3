"""Recurring items (confirmed income and bills): manual CRUD. Detection arrives in P4."""

import datetime as dt
from collections.abc import Mapping
from typing import Any

from app.db.base import ScopedTable
from app.db.client import Database
from app.domain.flows import as_date

TABLE = "recurring_items"
KINDS = frozenset({"income", "bill"})
CADENCES = frozenset({"weekly", "biweekly", "monthly", "semester", "custom"})
UPDATABLE = frozenset(
    {"name", "amount_sen", "cadence", "custom_interval_days", "anchor_date", "active"}
)


def _table(db: Database) -> ScopedTable:
    return ScopedTable(db, TABLE)


def _check_amount(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("amount_sen must be a positive whole number of sen")
    return value


def _check_name(value: object) -> str:
    name = value.strip() if isinstance(value, str) else ""
    if not name:
        raise ValueError("name is required")
    return name


def _check_cadence(cadence: object, interval: object) -> tuple[str, int | None]:
    if cadence not in CADENCES:
        raise ValueError(f"cadence must be one of {sorted(CADENCES)}")
    if cadence != "custom":
        return str(cadence), None  # an interval only means something for a custom cadence
    if isinstance(interval, bool) or not isinstance(interval, int) or interval <= 0:
        raise ValueError("a custom cadence needs custom_interval_days (a positive number of days)")
    return "custom", interval


def create(
    db: Database,
    user_id: str,
    *,
    kind: str,
    name: str,
    amount_sen: int,
    cadence: str,
    anchor_date: dt.date | str,
    custom_interval_days: int | None = None,
    active: bool = True,
) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    cadence, interval = _check_cadence(cadence, custom_interval_days)
    row = {
        "kind": kind,
        "name": _check_name(name),
        "amount_sen": _check_amount(amount_sen),
        "cadence": cadence,
        "custom_interval_days": interval,
        "anchor_date": as_date(anchor_date).isoformat(),
        "active": bool(active),
        "origin": "manual",
    }
    return _table(db).insert(user_id, row)


def get(db: Database, user_id: str, item_id: str) -> dict[str, Any] | None:
    return _table(db).get(user_id, item_id)


def list_items(db: Database, user_id: str, *, active_only: bool = False) -> list[dict[str, Any]]:
    filters = {"active": True} if active_only else {}
    return _table(db).list_rows(user_id, order_by="anchor_date", **filters)


def update(
    db: Database, user_id: str, item_id: str, patch: Mapping[str, Any]
) -> dict[str, Any] | None:
    unknown = set(patch) - UPDATABLE
    if unknown:
        raise ValueError(f"{sorted(unknown)} cannot be updated")
    current = get(db, user_id, item_id)
    if current is None:
        return None
    merged = {**current, **patch}
    cleaned: dict[str, Any] = {}
    if "name" in patch:
        cleaned["name"] = _check_name(patch["name"])
    if "amount_sen" in patch:
        cleaned["amount_sen"] = _check_amount(patch["amount_sen"])
    if "anchor_date" in patch:
        cleaned["anchor_date"] = as_date(patch["anchor_date"]).isoformat()
    if "active" in patch:
        cleaned["active"] = bool(patch["active"])
    if "cadence" in patch or "custom_interval_days" in patch:
        cadence, interval = _check_cadence(merged["cadence"], merged.get("custom_interval_days"))
        cleaned["cadence"], cleaned["custom_interval_days"] = cadence, interval
    return _table(db).update(user_id, item_id, cleaned)


def delete(db: Database, user_id: str, item_id: str) -> bool:
    """Deleting an item keeps its transactions; the database unlinks them (on delete set null)."""
    return _table(db).delete(user_id, item_id)
