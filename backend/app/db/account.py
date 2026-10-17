"""Everything one person owns, for "export my data" and "delete my data" (WP19).

`USER_TABLES` lists every table with a `user_id`, children before parents, so a delete never trips
a foreign key. A test checks it against the schema the fake knows, so a new table cannot be left
out by accident.
"""

from typing import Any

from app.db import user_settings
from app.db.base import ScopedTable, require_user_id
from app.db.client import Database

USER_TABLES = (
    "assistant_events",
    "assistant_actions",
    "transactions",
    "bnpl_installments",
    "bnpl_plans",
    "risk_checks",
    "recurring_items",
    "budgets",
    "user_categories",
    "provider_limits",
    "user_locks",
)
HIDDEN_USER_FIELDS = frozenset({"passphrase_hash", "token_version"})


def export(db: Database, user_id: str) -> dict[str, Any]:
    uid = require_user_id(user_id)
    user = db.table("users").select("*").eq("id", uid).limit(1).execute().data
    profile = {k: v for k, v in (user[0] if user else {}).items() if k not in HIDDEN_USER_FIELDS}
    tables = {table: ScopedTable(db, table).list_rows(uid) for table in USER_TABLES}
    return {"user": profile, "settings": user_settings.get(db, uid), "tables": tables}


def delete_everything(db: Database, user_id: str) -> dict[str, int]:
    """Remove every row the user owns in every table; reset their settings; keep the account."""
    uid = require_user_id(user_id)
    counts = {table: ScopedTable(db, table).delete_all(uid) for table in USER_TABLES}
    reset = {"onboarding_state": "new", "savings_buffer_sen": 0}
    db.table("user_settings").update(reset).eq("user_id", uid).execute()
    return counts
