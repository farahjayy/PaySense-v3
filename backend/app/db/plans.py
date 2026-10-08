"""BNPL plans and their instalments.

supabase-py has no multi-statement transactions, so every operation that needs two writes is
ordered so a failure can be undone, and it undoes itself:
  * `create_plan` writes plan -> instalments -> checkout payments; on any failure it deletes what
    it logged and then the plan (instalments cascade), and re-raises.
  * `mark_paid` logs the payment first, then flips the instalment with a CONDITIONAL update
    (`is_paid = false`); if the flip fails or loses a race, it deletes the payment it logged.
There is no stored balance to keep in step any more (ADR D-27): the only side effect of paying is
the linked expense transaction.
"""

import datetime as dt
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from app.db import transactions
from app.db.base import ScopedTable
from app.db.client import Database
from app.domain.categorize import BNPL
from app.domain.flows import as_date
from app.domain.plans import used_limit_sen
from app.domain.providers import PROVIDER_KEYS
from app.domain.schedule import Instalment

logger = logging.getLogger("paysense")

PLANS = "bnpl_plans"
INSTALMENTS = "bnpl_installments"
SCHEDULE_SOURCES = frozenset({"provider_rule", "manual"})
ITEM_NAME_LIMIT = 120
SUFFIX_SEPARATOR = " — "


class PlanError(Exception):
    """Base class for plan operations that cannot proceed."""


class AlreadyPaidError(PlanError):
    """The instalment is already marked paid."""


class PlanConflictError(PlanError):
    """Someone else changed the instalment while this request was in flight."""


class UnknownInstalmentError(PlanError, ValueError):
    """The plan has no instalment with that sequence number."""


def instalment_description(plan: Mapping[str, Any], seq: int) -> str:
    return (
        f"{plan['provider_label']} instalment {seq}/{plan['num_installments']}"
        f"{SUFFIX_SEPARATOR}{plan['item_name']}"
    )


def _checkout_description(plan: Mapping[str, Any]) -> str:
    return f"{plan['provider_label']} checkout payment{SUFFIX_SEPARATOR}{plan['item_name']}"


def _whole(value: object, field: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        kind = "positive" if minimum > 0 else "zero or more"
        raise ValueError(f"{field} must be a whole number of sen, {kind}")
    return value


def _check_name(value: object) -> str:
    name = value.strip() if isinstance(value, str) else ""
    if not name or len(name) > ITEM_NAME_LIMIT:
        raise ValueError(f"item_name must be 1-{ITEM_NAME_LIMIT} characters")
    return name


def _validate(plan: Mapping[str, Any], instalments: Sequence[Instalment]) -> dict[str, Any]:
    if plan.get("provider") not in PROVIDER_KEYS:
        raise ValueError(f"provider must be one of {list(PROVIDER_KEYS)}")
    label = plan.get("provider_label")
    if not isinstance(label, str) or not label.strip():
        raise ValueError("provider_label is required")
    if plan.get("schedule_source") not in SCHEDULE_SOURCES:
        raise ValueError(f"schedule_source must be one of {sorted(SCHEDULE_SOURCES)}")
    total = _whole(plan.get("total_price_sen"), "total_price_sen", minimum=1)
    upfront = _whole(plan.get("upfront_sen", 0), "upfront_sen", minimum=0)
    financed = _whole(plan.get("financed_sen"), "financed_sen", minimum=1)
    if financed + upfront != total:
        raise ValueError("financed_sen + upfront_sen must equal total_price_sen")
    if plan.get("num_installments") != len(instalments) or not instalments:
        raise ValueError("num_installments must match the number of instalments")
    if [i.seq for i in instalments] != list(range(1, len(instalments) + 1)):
        raise ValueError("instalment seq values must run 1..n in order")
    for instalment in instalments:
        _whole(instalment.amount_sen, "instalment amount_sen", minimum=1)
    first = as_date(plan["first_payment_date"])
    if first != instalments[0].due_date:
        raise ValueError("first_payment_date must equal the first instalment's due date")
    fee = plan.get("monthly_fee_rate_pct", 0)
    if isinstance(fee, bool) or not isinstance(fee, int | float) or fee < 0:
        raise ValueError("monthly_fee_rate_pct must be zero or more")
    return {
        "item_name": _check_name(plan.get("item_name")),
        "provider": plan["provider"],
        "provider_label": label.strip(),
        "schedule_source": plan["schedule_source"],
        "total_price_sen": total,
        "financed_sen": financed,
        "upfront_sen": upfront,
        "monthly_fee_rate_pct": fee,
        "num_installments": len(instalments),
        "purchase_date": as_date(plan["purchase_date"]).isoformat(),
        "first_payment_date": first.isoformat(),
        "risk_score_at_creation": plan.get("risk_score_at_creation"),
        "risk_check_id": plan.get("risk_check_id"),
        "risk_check_type": plan.get("risk_check_type"),
    }


def _log_payment(
    db: Database,
    user_id: str,
    plan: Mapping[str, Any],
    *,
    amount_sen: int,
    day: dt.date | str,
    description: str,
) -> dict[str, Any]:
    return transactions.create(
        db,
        user_id,
        date=day,
        amount_sen=amount_sen,
        type="expense",
        category=BNPL,
        description=description,
        is_bnpl=True,
        bnpl_plan_id=plan["id"],
    )


def create_plan(
    db: Database, user_id: str, plan: Mapping[str, Any], instalments: Sequence[Instalment]
) -> dict[str, Any]:
    """Create a plan with its schedule and log what was paid at checkout (an Atome first
    instalment, and any excess over the provider limit). All or nothing."""
    row = _validate(plan, instalments)
    plans = ScopedTable(db, PLANS)
    logged: list[str] = []
    created: dict[str, Any] | None = None
    try:
        created = plans.insert(user_id, row)
        purchase_day = row["purchase_date"]
        ScopedTable(db, INSTALMENTS).insert_many(
            user_id,
            [
                {
                    "plan_id": created["id"],
                    "seq": i.seq,
                    "due_date": i.due_date.isoformat(),
                    "amount_sen": i.amount_sen,
                    "is_paid": i.paid_at_checkout,
                    "paid_date": purchase_day if i.paid_at_checkout else None,
                }
                for i in instalments
            ],
        )
        if row["upfront_sen"] > 0:
            payment = _log_payment(
                db,
                user_id,
                created,
                amount_sen=row["upfront_sen"],
                day=purchase_day,
                description=_checkout_description(created),
            )
            logged.append(payment["id"])
        for instalment in instalments:
            if instalment.paid_at_checkout:
                payment = _log_payment(
                    db,
                    user_id,
                    created,
                    amount_sen=instalment.amount_sen,
                    day=purchase_day,
                    description=instalment_description(created, instalment.seq),
                )
                logged.append(payment["id"])
    except Exception:
        ScopedTable(db, "transactions").delete_many(user_id, logged)
        if created is not None:
            plans.delete(user_id, created["id"])  # instalments cascade
        raise
    result = get_with_instalments(db, user_id, created["id"])
    assert result is not None  # noqa: S101 - we just created it
    return result


def get_with_instalments(db: Database, user_id: str, plan_id: str) -> dict[str, Any] | None:
    plan = ScopedTable(db, PLANS).get(user_id, plan_id)
    if plan is None:
        return None
    rows = ScopedTable(db, INSTALMENTS).list_rows(user_id, order_by="seq", plan_id=plan_id)
    return {**plan, "installments": rows}


def list_with_instalments(db: Database, user_id: str) -> list[dict[str, Any]]:
    plans = ScopedTable(db, PLANS).list_rows(user_id, order_by="created_at", descending=True)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in ScopedTable(db, INSTALMENTS).list_rows(user_id, order_by="seq"):
        grouped.setdefault(row["plan_id"], []).append(row)
    return [{**plan, "installments": grouped.get(plan["id"], [])} for plan in plans]


def used_limits(db: Database, user_id: str) -> dict[str, int]:
    """Per provider, how much of its limit is in use (unpaid instalments; ADR D-28, ASSUMED)."""
    used: dict[str, int] = {}
    for plan in list_with_instalments(db, user_id):
        used[plan["provider"]] = used.get(plan["provider"], 0) + used_limit_sen(
            plan["installments"]
        )
    return used


def rename(db: Database, user_id: str, plan_id: str, new_name: str) -> dict[str, Any] | None:
    """Rename a plan and the descriptions it wrote; a description the user rewrote is left alone."""
    name = _check_name(new_name)
    plan = ScopedTable(db, PLANS).get(user_id, plan_id)
    if plan is None:
        return None
    old = plan["item_name"]
    if name != old:
        ScopedTable(db, PLANS).update(user_id, plan_id, {"item_name": name})
        old_suffix, new_suffix = f"{SUFFIX_SEPARATOR}{old}", f"{SUFFIX_SEPARATOR}{name}"
        for txn in transactions.list_for_plan(db, user_id, plan_id):
            description = txn.get("description") or ""
            if not description.endswith(old_suffix):
                continue
            try:
                transactions.update(
                    db,
                    user_id,
                    txn["id"],
                    {"description": description[: -len(old_suffix)] + new_suffix},
                )
            except Exception:
                logger.exception("Couldn't rename transaction %s for plan %s", txn["id"], plan_id)
    return get_with_instalments(db, user_id, plan_id)


def delete(db: Database, user_id: str, plan_id: str, *, keep_payments: bool = True) -> bool:
    """Delete a plan. Logged payments are kept (unlinked by the database) unless asked."""
    if ScopedTable(db, PLANS).get(user_id, plan_id) is None:
        return False
    if not keep_payments:
        transactions.delete_for_plan(db, user_id, plan_id)
    return ScopedTable(db, PLANS).delete(user_id, plan_id)


def mark_paid(
    db: Database, user_id: str, plan_id: str, seq: int, paid_date: dt.date
) -> dict[str, Any] | None:
    """Mark one instalment paid and log it as an expense. None if the plan or seq is not found."""
    plan = ScopedTable(db, PLANS).get(user_id, plan_id)
    if plan is None:
        return None
    instalments = ScopedTable(db, INSTALMENTS)
    rows = instalments.list_rows(user_id, plan_id=plan_id, seq=seq)
    if not rows:
        return None
    instalment = rows[0]
    if instalment["is_paid"]:
        raise AlreadyPaidError(f"instalment {seq} is already paid")
    payment = _log_payment(
        db,
        user_id,
        plan,
        amount_sen=instalment["amount_sen"],
        day=paid_date,
        description=instalment_description(plan, seq),
    )
    try:
        flipped = instalments.update(
            user_id,
            instalment["id"],
            {"is_paid": True, "paid_date": paid_date.isoformat()},
            where={"is_paid": False},
        )
    except Exception:
        transactions.delete(db, user_id, payment["id"])
        raise
    if flipped is None:
        transactions.delete(db, user_id, payment["id"])
        raise PlanConflictError(f"instalment {seq} changed while it was being paid")
    return flipped


def mark_paid_many(
    db: Database, user_id: str, plan_id: str, seqs: Sequence[int], paid_date: dt.date
) -> list[dict[str, Any]]:
    """Mark several instalments paid, in order. Everything is checked before anything is paid."""
    if ScopedTable(db, PLANS).get(user_id, plan_id) is None:
        return []
    existing = {
        row["seq"]: row for row in ScopedTable(db, INSTALMENTS).list_rows(user_id, plan_id=plan_id)
    }
    wanted = sorted(set(seqs))
    missing = [seq for seq in wanted if seq not in existing]
    if missing:
        raise UnknownInstalmentError(f"seq {missing} not found in this plan")
    already = [seq for seq in wanted if existing[seq]["is_paid"]]
    if already:
        raise AlreadyPaidError(f"instalments {already} are already paid")
    results = []
    for seq in wanted:
        paid = mark_paid(db, user_id, plan_id, seq, paid_date)
        if paid is not None:
            results.append(paid)
    return results
