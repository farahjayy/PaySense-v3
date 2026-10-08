"""Monthly bill grouping: instalments due across every tracked plan, by calendar month.

Powers the "My bills" list: how much is due each month and whether it is fully paid. Order: the
current month first (only if something is actually due in it — no synthetic RM0 row), then past
months going backward, then upcoming months going forward. Port of v1 `services/bills.py`, in sen.
"""

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from app.domain.flows import as_date


def _month_key(due: date) -> str:
    return due.strftime("%Y-%m")


def monthly_bills(
    plans: Iterable[Mapping[str, Any]], today: date
) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for plan in plans:
        for instalment in plan["installments"]:
            due = as_date(instalment["due_date"])
            buckets.setdefault(_month_key(due), []).append(
                {
                    "plan_id": plan["id"],
                    "item_name": plan["item_name"],
                    "provider": plan["provider"],
                    "provider_label": plan.get("provider_label", plan["provider"]),
                    "seq": instalment["seq"],
                    "amount_sen": instalment["amount_sen"],
                    "due_date": due.isoformat(),
                    "is_paid": instalment["is_paid"],
                }
            )

    current = _month_key(today)
    past = sorted(k for k in buckets if k < current)
    future = sorted(k for k in buckets if k > current)
    ordered_keys = ([current] if current in buckets else []) + list(reversed(past)) + future

    months = []
    for month in ordered_keys:
        items = sorted(buckets[month], key=lambda i: (i["due_date"], i["item_name"]))
        months.append(
            {
                "month": month,
                "is_current": month == current,
                "total_due_sen": sum(i["amount_sen"] for i in items),
                "paid_total_sen": sum(i["amount_sen"] for i in items if i["is_paid"]),
                "fully_paid": all(i["is_paid"] for i in items),
                "has_overdue": any(
                    not i["is_paid"] and i["due_date"] < today.isoformat() for i in items
                ),
                "items": items,
            }
        )
    return {"months": months}
