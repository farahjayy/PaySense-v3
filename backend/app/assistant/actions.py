"""Pending actions (ADR D-48): how the assistant gets a write done without ever making it.

propose  the payload is validated with the API's own model and the checks its route makes, the
         server writes the summary from the validated payload, and the action is stored per user
         with a digest of its canonical payload and an expiry. An identical pending proposal is
         reused.
confirm  same user (scoped read), not expired, still pending (claimed by an atomic status change,
         so a replay or a double click gets 409), payload re-validated and its digest re-checked,
         a per-user lock and a 120-second duplicate window; then the Tier 2 function runs.
decline  pending -> declined, atomically.
Every step is written to the audit log.
"""

import datetime as dt
import hashlib
import json
import threading
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from app.api import budgets as budgets_api
from app.api.assistant import ActionResultOut, PendingActionOut
from app.api.plans import preview_out, propose_for
from app.api.transactions import _require_own_recurring_item
from app.assistant.context import ToolContext
from app.assistant.writes import WRITE_FUNCTIONS
from app.core.errors import api_error, not_found, unprocessable
from app.db import assistant_actions as actions_repo
from app.db import assistant_events as events
from app.db import budgets as budgets_repo
from app.domain.money import format_rm
from app.domain.providers import get_provider

# confirm_import is not here: only the paste parser (WP4d) may propose it, after grounding rows.
ModelProposable = Literal["add_transaction", "create_plan", "set_budget", "delete_budget"]
DUPLICATE_WINDOW_SECONDS = 120
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_ACTION_OUT: TypeAdapter[Any] = TypeAdapter(PendingActionOut)


class ProposeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ModelProposable
    payload: dict[str, Any]


def canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _when(value: Any) -> dt.datetime:
    stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=dt.UTC)


def _date_text(day: dt.date) -> str:
    return f"{day.day} {day.strftime('%b %Y')}"


# ------------------------------------------------------------------ validation and summaries
def validate_payload(
    ctx: ToolContext, type_: str, payload: dict[str, Any]
) -> tuple[BaseModel, dict[str, Any] | None, str]:
    """(validated model, preview for the card, summary sentence) or a 422/404 HTTPException."""
    write = WRITE_FUNCTIONS[type_]
    try:
        model = write.payload_model.model_validate(payload)
    except ValidationError as err:
        first = err.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "payload"
        raise unprocessable("invalid_payload", f"{where}: {first['msg']}") from err
    preview: dict[str, Any] | None = None
    if type_ == "add_transaction":
        _require_own_recurring_item(ctx.db, ctx.user_id, model.recurring_item_id)
        what = f" ({model.description})" if model.description else ""
        summary = (
            f"Add {model.type} of {format_rm(model.amount_sen)} in {model.category} on "
            f"{_date_text(model.date)}{what}."
        )
    elif type_ == "confirm_import":
        money_in = sum(r.amount_sen for r in model.rows if r.type == "income")
        money_out = sum(r.amount_sen for r in model.rows if r.type != "income")
        summary = (
            f"Add {len(model.rows)} transaction(s): {format_rm(money_in)} in, "
            f"{format_rm(money_out)} out."
        )
    elif type_ == "create_plan":
        from app.api.risk import _check_purchase_date

        _check_purchase_date(model, ctx.today)
        plan = preview_out(propose_for(model, ctx.db, ctx.user_id))
        preview = plan.model_dump(mode="json")
        label = plan.provider_label or get_provider(plan.provider).label
        summary = (
            f"Create a {label} plan for {model.item_name}: {format_rm(plan.total_price_sen)} "
            f"in {plan.num_installments} instalment(s), first due "
            f"{_date_text(plan.first_payment_date)}, total cost {format_rm(plan.total_cost_sen)}. "
            "The risk check runs again before it is saved."
        )
    elif type_ == "set_budget":
        model = model.model_copy(update={"category": budgets_api.clean_category(model.category)})
        summary = f"Set the {model.category} budget to {format_rm(model.limit_sen)} a month."
    else:  # delete_budget
        found = budgets_repo.find(ctx.db, ctx.user_id, model.category.strip())
        if found is None:
            raise not_found("budget_not_found", "There is no budget for that category.")
        summary = (
            f"Remove the {found['category']} budget ({format_rm(found['limit_sen'])} a month)."
        )
    return model, preview, summary


def action_out(row: dict[str, Any]) -> Any:
    return _ACTION_OUT.validate_python(
        {
            "id": row["id"],
            "type": row["type"],
            "status": row["status"],
            "summary": row["summary"],
            "expires_at": row["expires_at"],
            "payload": row["payload"],
            **({"preview": row.get("preview")} if row["type"] == "create_plan" else {}),
        }
    )


# ------------------------------------------------------------------ propose
def propose(
    ctx: ToolContext, type_: str, payload: dict[str, Any], *, origin: str = "model"
) -> dict[str, Any]:
    """Validate and store a pending action; reuse an identical one that is still pending."""
    model, preview, summary = validate_payload(ctx, type_, payload)
    stored = model.model_dump(mode="json")
    key = digest(stored)
    existing = actions_repo.find_pending(ctx.db, ctx.user_id, type_, key)
    if existing is not None and _when(existing["expires_at"]) > _now():
        return existing
    ttl = dt.timedelta(minutes=ctx.settings.assistant_action_ttl_minutes)
    row = actions_repo.create(
        ctx.db,
        ctx.user_id,
        type=type_,
        payload=stored,
        digest=key,
        summary=summary,
        expires_at=_now() + ttl,
        preview=preview,
    )
    events.record(
        ctx.db,
        ctx.user_id,
        "proposal",
        tier=1,
        tool=type_,
        status="pending",
        action_id=row["id"],
        detail={"origin": origin, "summary": summary},
    )
    return row


# ------------------------------------------------------------------ confirm / decline
def _lock(user_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(user_id, threading.Lock())


def _load(ctx: ToolContext, action_id: str) -> dict[str, Any]:
    row = actions_repo.get(ctx.db, ctx.user_id, action_id)  # another user's id finds nothing
    if row is None:
        raise not_found("action_not_found", "No such proposal.")
    return row


def _not_pending(row: dict[str, Any]) -> HTTPException:
    return api_error(
        409, "action_not_pending", f"This proposal is already {row['status']}; it can be used once."
    )


def _result(row: dict[str, Any], status: str, message: str, **fields: Any) -> ActionResultOut:
    return ActionResultOut(id=row["id"], type=row["type"], status=status, message=message, **fields)


def confirm(ctx: ToolContext, action_id: str) -> ActionResultOut:
    row = _load(ctx, action_id)
    if row["status"] != "pending":
        events.record(
            ctx.db,
            ctx.user_id,
            "refusal",
            tier=2,
            tool=row["type"],
            status="not_pending",
            action_id=row["id"],
        )
        raise _not_pending(row)
    if _when(row["expires_at"]) <= _now():
        actions_repo.transition(ctx.db, ctx.user_id, row["id"], expected="pending", to="expired")
        events.record(
            ctx.db,
            ctx.user_id,
            "refusal",
            tier=2,
            tool=row["type"],
            status="expired",
            action_id=row["id"],
        )
        raise api_error(410, "action_expired", "This proposal has expired. Ask again.")
    lock = _lock(ctx.user_id)
    if not lock.acquire(blocking=False):
        raise api_error(409, "confirm_in_progress", "Something is already being saved. Wait.")
    try:
        if actions_repo.recent_confirmed(
            ctx.db,
            ctx.user_id,
            row["type"],
            row["payload_digest"],
            _now() - dt.timedelta(seconds=DUPLICATE_WINDOW_SECONDS),
        ):
            raise api_error(409, "duplicate_confirm", "This was just done. Check before repeating.")
        claimed = actions_repo.transition(
            ctx.db, ctx.user_id, row["id"], expected="pending", to="confirmed"
        )
        if claimed is None:  # someone else (another tab, a replay) got there first
            raise _not_pending(actions_repo.get(ctx.db, ctx.user_id, row["id"]) or row)
        try:
            if digest(row["payload"]) != row["payload_digest"]:
                raise api_error(
                    422, "action_tampered", "This proposal was changed after it was made."
                )
            model, _, _ = validate_payload(ctx, row["type"], row["payload"])
            fields = WRITE_FUNCTIONS[row["type"]].run(ctx, model)
        except Exception as err:
            reason = (
                err.detail.get("message")
                if isinstance(err, HTTPException) and isinstance(err.detail, dict)
                else "The change could not be saved."
            )
            actions_repo.transition(
                ctx.db,
                ctx.user_id,
                row["id"],
                expected="confirmed",
                to="failed",
                result={"error": reason},
            )
            events.record(
                ctx.db,
                ctx.user_id,
                "confirm",
                tier=2,
                tool=row["type"],
                status="failed",
                action_id=row["id"],
                detail={"error": reason},
            )
            raise
        result = _result(row, "confirmed", fields.pop("message"), **fields)
        actions_repo.transition(
            ctx.db,
            ctx.user_id,
            row["id"],
            expected="confirmed",
            to="confirmed",
            result={"message": result.message},
        )
        events.record(
            ctx.db,
            ctx.user_id,
            "confirm",
            tier=2,
            tool=row["type"],
            status="ok",
            action_id=row["id"],
            detail={"summary": row["summary"]},
        )
        return result
    finally:
        lock.release()


def decline(ctx: ToolContext, action_id: str) -> ActionResultOut:
    row = _load(ctx, action_id)
    changed = actions_repo.transition(
        ctx.db, ctx.user_id, row["id"], expected="pending", to="declined"
    )
    if changed is None:
        raise _not_pending(row)
    events.record(
        ctx.db,
        ctx.user_id,
        "decline",
        tier=2,
        tool=row["type"],
        status="declined",
        action_id=row["id"],
    )
    return _result(row, "declined", "Nothing was changed.")
