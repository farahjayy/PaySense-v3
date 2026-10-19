"""Sign-in audit log (ADR D-69): sign-up, login, failed login and logout. Insert-only.

A failed login has no user, so its row has no `user_id`; every other row is the user's own and is
exported and deleted with their data (`db/account.py`).
"""

from typing import Any

from app.db.base import require_user_id
from app.db.client import Database

TABLE = "auth_events"
EVENTS = frozenset({"signup", "login", "login_failed", "logout"})
REASONS = frozenset({"cancelled", "state", "exchange", "token"})
MAX_USER_AGENT = 500


def record(
    db: Database,
    event: str,
    *,
    user_id: str | None = None,
    email: str | None = None,
    reason: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    if event not in EVENTS:
        raise ValueError(f"unknown auth event: {event}")
    if (reason is not None) != (event == "login_failed") or (reason and reason not in REASONS):
        raise ValueError("a reason is given for a failed login only, from the known reasons")
    row: dict[str, Any] = {
        "event": event,
        "email": email,
        "reason": reason,
        "ip": ip,
        "user_agent": user_agent[:MAX_USER_AGENT] if user_agent else None,
    }
    if user_id is not None:
        row["user_id"] = require_user_id(user_id)
    db.table(TABLE).insert(row).execute()
