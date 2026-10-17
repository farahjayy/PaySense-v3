"""The assistant's audit log (ADR D-48): what was asked, which tools ran at which tier, what was
proposed, confirmed, declined or refused, and every fallback. User-scoped. Never holds a key."""

from typing import Any

from app.db.base import PAGE_SIZE, ScopedTable
from app.db.client import Database

TABLE = "assistant_events"
KINDS = frozenset(
    {"message", "reply", "tool_call", "proposal", "confirm", "decline", "refusal", "fallback",
     "error"}
)  # fmt: skip
MAX_TEXT = 2000  # free text in `detail` is cut to this many characters


def _short(value: Any) -> Any:
    if isinstance(value, str):
        return value[:MAX_TEXT]
    if isinstance(value, dict):
        return {k: _short(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_short(v) for v in value[:50]]
    return value


def record(
    db: Database,
    user_id: str,
    kind: str,
    *,
    tier: int | None = None,
    tool: str | None = None,
    status: str | None = None,
    action_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    return ScopedTable(db, TABLE).insert(
        user_id,
        {
            "kind": kind,
            "tier": tier,
            "tool": tool,
            "status": status,
            "action_id": action_id,
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "detail": _short(detail) if detail else None,
        },
    )


def list_events(db: Database, user_id: str) -> list[dict[str, Any]]:
    return ScopedTable(db, TABLE).list_rows(user_id, order_by="created_at")


def _total(rows: list[dict[str, Any]]) -> int:
    return sum(int(r.get("input_tokens") or 0) + int(r.get("output_tokens") or 0) for r in rows)


def tokens_since(db: Database, user_id: str, since_iso: str) -> int:
    """Tokens one user's replies used since `since_iso` (the per-user daily budget)."""
    rows = ScopedTable(db, TABLE).list_rows(
        user_id, kind="reply", between={"created_at": (since_iso, None)},
        columns="input_tokens,output_tokens",
    )  # fmt: skip
    return _total(rows)


def global_tokens_since(db: Database, since_iso: str) -> int:
    """Tokens every user's replies used since `since_iso`: the global daily cost cap.

    The one deliberately unscoped read of this table (like `users.get_by_username`): it reads two
    token counts per row and nothing else, so no user's content can leave through it. Paged past
    PostgREST's 1000-row cap so the cap cannot be undercounted."""
    total, start = 0, 0
    while True:
        page = (
            db.table(TABLE)
            .select("input_tokens,output_tokens")
            .eq("kind", "reply")
            .gte("created_at", since_iso)
            .order("id")
            .range(start, start + PAGE_SIZE - 1)
            .execute()
            .data
        )
        total += _total(page)
        if len(page) < PAGE_SIZE:
            return total
        start += PAGE_SIZE
