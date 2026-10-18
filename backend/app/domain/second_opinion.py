"""The Second-Opinion Check's pure parts (ADR D-57): every unpaid instalment across providers
stacked by month with the new plan, the exposure before and after, and the added chance of
running short. No I/O; every amount is integer sen from the plans, the plan rules or the ledger.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.domain.flows import as_date

# BNM's policy document on personal financing asks banks for a full affordability assessment once
# a consumer's BNPL limits across providers add up to RM1,500. Shown as information about the
# student's own recorded limits, never as a compliance statement.
BNM_LIMIT_LINE_SEN = 150_000


@dataclass(frozen=True)
class StackMonth:
    month: str  # "YYYY-MM"
    by_provider: tuple[tuple[str, int], ...]  # (provider label, unpaid sen due), by label
    new_plan_sen: int
    total_sen: int
    known_income_sen: int  # confirmed recurring income falling in the month


@dataclass(frozen=True)
class Exposure:
    unpaid_before_sen: int
    unpaid_after_sen: int
    providers_before: tuple[str, ...]
    providers_after: tuple[str, ...]
    plans_before: int
    plans_after: int
    recorded_limits_sen: int | None
    reaches_bnm_line: bool | None


def _key(day: date) -> str:
    return day.strftime("%Y-%m")


def _unpaid(plans: Iterable[Mapping[str, Any]]) -> list[tuple[str, date, int]]:
    """(provider label, due date, sen) for every instalment not yet paid."""
    out = []
    for plan in plans:
        label = plan.get("provider_label") or plan["provider"]
        for instalment in plan["installments"]:
            if not instalment["is_paid"]:
                out.append((label, as_date(instalment["due_date"]), instalment["amount_sen"]))
    return out


def _months(first: str, last: str) -> list[str]:
    year, month = int(first[:4]), int(first[5:])
    out = []
    while f"{year:04d}-{month:02d}" <= last:
        out.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def stack_dues(
    plans: Iterable[Mapping[str, Any]],
    new_instalments: Sequence[tuple[date, int]],
    income_by_month: Mapping[str, int],
    today: date,
) -> list[StackMonth]:
    """Every month from this one to the new plan's last instalment. An unpaid instalment whose due
    date has passed (an existing plan's, or the new plan's when its purchase date is in the past)
    is still owed, so it sits in the current month."""
    current = _key(today)
    owed: dict[str, dict[str, int]] = {}
    for label, due, sen in _unpaid(plans):
        month = max(_key(due), current)
        owed.setdefault(month, {})
        owed[month][label] = owed[month].get(label, 0) + sen
    new: dict[str, int] = {}
    for due, sen in new_instalments:
        month = max(_key(due), current)
        new[month] = new.get(month, 0) + sen
    last = max([current, *new])
    months = []
    for month in _months(current, last):
        by_provider = tuple(sorted(owed.get(month, {}).items()))
        existing = sum(sen for _, sen in by_provider)
        months.append(
            StackMonth(
                month=month,
                by_provider=by_provider,
                new_plan_sen=new.get(month, 0),
                total_sen=existing + new.get(month, 0),
                known_income_sen=int(income_by_month.get(month, 0)),
            )
        )
    return months


def exposure(
    plans: Iterable[Mapping[str, Any]],
    new_payable_sen: int,
    new_label: str,
    provider_limits: Mapping[str, int | None],
) -> Exposure:
    plans = list(plans)
    unpaid = _unpaid(plans)
    owing = [p for p in plans if any(not i["is_paid"] for i in p["installments"])]
    before = tuple(sorted({label for label, _, _ in unpaid}))
    after = tuple(sorted({*before, new_label}))
    recorded = [limit for limit in provider_limits.values() if limit is not None]
    total_limits = sum(recorded) if recorded else None
    return Exposure(
        unpaid_before_sen=sum(sen for _, _, sen in unpaid),
        unpaid_after_sen=sum(sen for _, _, sen in unpaid) + new_payable_sen,
        providers_before=before,
        providers_after=after,
        plans_before=len(owing),
        plans_after=len(owing) + 1,
        recorded_limits_sen=total_limits,
        reaches_bnm_line=None if total_limits is None else total_limits >= BNM_LIMIT_LINE_SEN,
    )


def added_probability(with_purchase: float | None, without: float | None) -> float | None:
    """The simulated chance of running short with the purchase minus without it. Both come from
    one simulation with one seed, so the purchase cannot lower it; a negative difference would be
    rounding and is shown as zero."""
    if with_purchase is None or without is None:
        return None
    return max(with_purchase - without, 0.0)
