"""Frozen risk-check reports. Written once when the student goes ahead with the purchase; never
updated, so the report they saw is the report they can read back (ADR D-30)."""

from typing import Any

from app.db.base import ScopedTable
from app.db.client import Database

TABLE = "risk_checks"
LABELS = {"Safe": "safe", "Caution": "caution", "At Risk": "at_risk"}
BANDS = {label: band for band, label in LABELS.items()}
REQUIRED = (
    "input",
    "features",
    "feature_schema_hash",
    "model_version",
    "p",
    "p_simulated",
    "score",
    "label",
    "factors",
)


def _table(db: Database) -> ScopedTable:
    return ScopedTable(db, TABLE)


def _validate(row: dict[str, Any]) -> None:
    missing = [key for key in REQUIRED if key not in row]
    if missing:
        raise ValueError(f"risk check is missing {missing}")
    for key in ("p", "p_simulated"):
        value = row[key]
        if isinstance(value, bool) or not isinstance(value, int | float) or not 0 <= value <= 1:
            raise ValueError(f"{key} must be a probability between 0 and 1")
    score = row["score"]
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        raise ValueError("score must be a whole number from 0 to 100")
    if row["label"] not in BANDS:
        raise ValueError(f"label must be one of {sorted(BANDS)}")


def create(db: Database, user_id: str, row: dict[str, Any]) -> dict[str, Any]:
    _validate(row)
    return _table(db).insert(user_id, row)


def get(db: Database, user_id: str, check_id: str) -> dict[str, Any] | None:
    return _table(db).get(user_id, check_id)


def delete(db: Database, user_id: str, check_id: str) -> bool:
    return _table(db).delete(user_id, check_id)
