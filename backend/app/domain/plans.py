"""Plan status derivation and read-model enrichment, in sen (port of v1 `services/plans.py`).

v1's balance adjustment on plan creation is deliberately not ported: v2 stores no balance (D-27).
"""

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from app.domain.flows import as_date


def derive_status(instalments: Iterable[Mapping[str, Any]], today: date) -> str:
    items = list(instalments)
    if items and all(i["is_paid"] for i in items):
        return "completed"
    if any(not i["is_paid"] and as_date(i["due_date"]) < today for i in items):
        return "overdue"
    return "active"


def enrich_plan(
    plan: Mapping[str, Any], instalments: Iterable[Mapping[str, Any]], today: date
) -> dict[str, Any]:
    """A new plan dict with computed fields; inputs are not mutated.

    `total_payable_sen` is the sum of the real instalments — never a re-derived formula.
    """
    ordered = sorted(instalments, key=lambda i: i["seq"])
    paid = [i for i in ordered if i["is_paid"]]
    unpaid = [i for i in ordered if not i["is_paid"]]
    next_due = min((as_date(i["due_date"]) for i in unpaid), default=None)
    return {
        **plan,
        "status": derive_status(ordered, today),
        "installment_amount_sen": ordered[0]["amount_sen"] if ordered else 0,
        "total_payable_sen": sum(i["amount_sen"] for i in ordered),
        "paid_count": len(paid),
        "remaining_count": len(unpaid),
        "next_due_date": next_due.isoformat() if next_due else None,
    }


def used_limit_sen(instalments: Iterable[Mapping[str, Any]]) -> int:
    """How much of a provider's limit is in use: the sum of its still-unpaid instalments.

    ASSUMED (PRD §8 Q9, ADR D-28): providers count the unpaid instalment amounts, fee included,
    against the limit. Confirm with a real checkout; this is the one place to change.
    """
    return sum(i["amount_sen"] for i in instalments if not i["is_paid"])


def remaining_limit_sen(limit_sen: int | None, used_sen: int) -> int | None:
    """What is left of a recorded limit (never negative); None when no limit is recorded."""
    if limit_sen is None:
        return None
    return max(limit_sen - used_sen, 0)
