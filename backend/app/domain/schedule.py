"""Instalment schedules, in integer sen end to end (ADR D-16).

The fee is a MONTHLY rate: total = price x (1 + monthly_rate/100 x instalments), rounded to the
nearest sen (half up). Each instalment is the total divided by the count rounded DOWN to the sen,
with the leftover sen in the LAST instalment, so instalments always sum to the total exactly.
Ported from v1's `services/schedule.py` (whose behaviour its tests pin) minus the float edges.

Two v2 additions:
  * `split_for_limit` (ADR D-28): a provider's remaining limit caps how much of a purchase can be
    financed; the rest is paid at checkout.
  * `build_manual_schedule` (ADR D-24): the "Other provider" path — dates and amounts are exactly
    what the user typed from their own checkout; no provider rule, no fee formula.
"""

from dataclasses import dataclass
from datetime import date

from app.domain.money import percent_to_hundredths
from app.domain.providers import get_provider

RATE_SCALE = 10_000  # 100% in hundredths-of-a-percent arithmetic
MIN_INSTALMENTS = 1
MAX_INSTALMENTS = 36  # matches the bnpl_plans check constraint


@dataclass(frozen=True)
class Instalment:
    seq: int
    due_date: date
    amount_sen: int
    paid_at_checkout: bool = False


@dataclass(frozen=True)
class LimitSplit:
    """How a purchase divides under a provider limit (ADR D-28)."""

    financed_sen: int  # the part put on the provider (its price, before any fee)
    upfront_sen: int  # the part paid at checkout because the limit cannot cover it
    total_payable_sen: int  # what the financed part costs to repay, fee included
    limit_applied: bool  # False when no limit was known


def _check_count(count: int) -> None:
    if not MIN_INSTALMENTS <= count <= MAX_INSTALMENTS:
        raise ValueError(f"instalments must be between {MIN_INSTALMENTS} and {MAX_INSTALMENTS}")


def total_payable_sen(price_sen: int, monthly_rate_pct: float | str, num_instalments: int) -> int:
    """Price plus the monthly fee for every instalment month, to the nearest sen (half up)."""
    rate_hundredths = percent_to_hundredths(monthly_rate_pct)
    numerator = price_sen * (RATE_SCALE + rate_hundredths * num_instalments)
    return (numerator + RATE_SCALE // 2) // RATE_SCALE


def split_sen(total_sen: int, num_instalments: int) -> list[int]:
    """Equal instalments rounded down to the sen; leftover sen go in the last one."""
    base = total_sen // num_instalments
    return [base] * (num_instalments - 1) + [total_sen - base * (num_instalments - 1)]


def add_months(start: date, months: int) -> date:
    """Month arithmetic that clamps to the last valid day (31 Jan + 1 month = 28/29 Feb)."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(start.day, _days_in_month(year, month)))


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def default_first_payment_date(provider_key: str, purchase_date: date) -> date:
    """First due date implied by the provider's billing rule (app/domain/providers.py)."""
    config = get_provider(provider_key)
    if config.start_rule == "months_after_purchase":
        return add_months(purchase_date, config.start_offset_months)
    return purchase_date


def is_paid_at_checkout(provider_key: str, first_payment_date: date, purchase_date: date) -> bool:
    """True when the first instalment is charged at checkout (Atome, unless moved later)."""
    return (
        get_provider(provider_key).checkout_instalments > 0 and first_payment_date == purchase_date
    )


def generate_schedule(
    price_sen: int,
    monthly_rate_pct: float | str,
    num_instalments: int,
    first_payment_date: date,
    checkout_instalments: int = 0,
) -> list[Instalment]:
    """Instalments whose amounts sum to the total payable exactly."""
    _check_count(num_instalments)
    if price_sen <= 0:
        raise ValueError("price must be positive")
    total = total_payable_sen(price_sen, monthly_rate_pct, num_instalments)
    if total < num_instalments:
        raise ValueError(f"price is too small to split into {num_instalments} instalments")
    amounts = split_sen(total, num_instalments)
    return [
        Instalment(
            seq=seq,
            due_date=add_months(first_payment_date, seq - 1),
            amount_sen=amounts[seq - 1],
            paid_at_checkout=seq <= checkout_instalments,
        )
        for seq in range(1, num_instalments + 1)
    ]


def build_schedule(
    provider_key: str,
    price_sen: int,
    monthly_rate_pct: float | str,
    num_instalments: int,
    purchase_date: date,
    first_payment_date: date | None = None,
) -> list[Instalment]:
    """Provider-aware schedule for the rule-driven providers.

    An explicit `first_payment_date` (the user's real due date) overrides the provider default.
    A provider whose config has no monthly fee ignores the rate.
    """
    config = get_provider(provider_key)
    rate = monthly_rate_pct if config.monthly_fee_applies else 0
    first_due = first_payment_date or default_first_payment_date(provider_key, purchase_date)
    checkout = (
        config.checkout_instalments
        if is_paid_at_checkout(provider_key, first_due, purchase_date)
        else 0
    )
    return generate_schedule(
        price_sen, rate, num_instalments, first_due, checkout_instalments=checkout
    )


def split_for_limit(
    price_sen: int,
    remaining_limit_sen: int | None,
    monthly_rate_pct: float | str,
    num_instalments: int,
) -> LimitSplit:
    """Divide a purchase between the provider and the checkout counter (ADR D-28).

    ASSUMED (PRD §8 Q9, to be confirmed against a real checkout): the limit caps the financed
    TOTAL PAYABLE, fee included, so the financed amount is the largest principal whose price plus
    fee fits the remaining limit. With no known limit nothing is capped. An exhausted or
    overdrawn limit finances nothing; the caller rejects the plan.
    """
    _check_count(num_instalments)
    if price_sen <= 0:
        raise ValueError("price must be positive")
    if remaining_limit_sen is None:
        total = total_payable_sen(price_sen, monthly_rate_pct, num_instalments)
        return LimitSplit(price_sen, 0, total, limit_applied=False)

    remaining = max(remaining_limit_sen, 0)
    low, high = 0, price_sen  # total payable is non-decreasing in the principal: binary search
    while low < high:
        middle = (low + high + 1) // 2
        if total_payable_sen(middle, monthly_rate_pct, num_instalments) <= remaining:
            low = middle
        else:
            high = middle - 1
    return LimitSplit(
        financed_sen=low,
        upfront_sen=price_sen - low,
        total_payable_sen=total_payable_sen(low, monthly_rate_pct, num_instalments),
        limit_applied=True,
    )


def _split_typed_total(total: int | None, num_instalments: int) -> list[int]:
    if total is None or total <= 0:
        raise ValueError("total payable must be positive")
    if total < num_instalments:
        raise ValueError(f"total payable is too small to split into {num_instalments} instalments")
    return split_sen(total, num_instalments)


def build_manual_schedule(
    first_payment_date: date,
    num_instalments: int,
    *,
    instalment_sen: int | None = None,
    total_payable_sen: int | None = None,
) -> list[Instalment]:
    """The "Other provider" schedule: exactly what the user typed, nothing inferred (ADR D-24).

    Give either the instalment amount (all instalments equal) or the total payable (split exactly,
    leftover sen in the last). No provider rule, no fee formula, nothing paid at checkout.
    """
    _check_count(num_instalments)
    if (instalment_sen is None) == (total_payable_sen is None):
        raise ValueError("provide exactly one of instalment_sen or total_payable_sen")
    if instalment_sen is not None:
        if instalment_sen <= 0:
            raise ValueError("instalment amount must be positive")
        amounts = [instalment_sen] * num_instalments
    else:
        amounts = _split_typed_total(total_payable_sen, num_instalments)
    return [
        Instalment(seq=seq, due_date=add_months(first_payment_date, seq - 1), amount_sen=amount)
        for seq, amount in enumerate(amounts, start=1)
    ]
