"""Fixed bills (plan P2, A5): rent, phone and subscriptions, each on an exact monthly date.

Descriptions are worded so the importer's first-match categoriser (`domain.categorize`) reads them
as the intended category, which the tests assert. Alongside the events the generator returns the
ground-truth recurring items used later to score recurring-bill detection.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from ml.datagen.calendar import day_in_month, iter_month_starts
from ml.datagen.params import Params
from ml.datagen.types import RecurringTruth, Txn

RENT_TEMPLATES = ("Hostel rent", "Rent - bilik sewa", "Sewa bilik")
PHONE_TEMPLATES = ("Maxis bill", "Unifi Mobile Bill", "Celcom bill", "Digi bill")
SUBSCRIPTION_TEMPLATES = (
    "Netflix subscription",
    "Spotify Premium",
    "Astro subscription",
    "iCloud storage",
)
MAX_SUBSCRIPTIONS = 2


@dataclass
class BillsResult:
    events: list[Txn] = field(default_factory=list)
    truth: list[RecurringTruth] = field(default_factory=list)


def _between(rng: np.random.Generator, low_high: list[int]) -> int:
    low, high = low_high
    return int(rng.integers(low, high + 1))


def _monthly(
    start: date,
    end: date,
    day: int,
    name: str,
    category: str,
    typical_sen: int,
    amounts: Callable[[], int],
    out: BillsResult,
) -> None:
    """One bill per month on `day`. The ground truth records the TYPICAL amount (the level the
    bill varies around), not whichever month happened to be generated last."""
    first = None
    for month in iter_month_starts(start, end):
        when = day_in_month(month.year, month.month, day)
        if start <= when <= end:
            out.events.append(Txn(when, amounts(), "expense", category, name))
            first = first or when
    if first:
        out.truth.append(RecurringTruth(name, "bill", typical_sen, "monthly", first))


def generate_bills(params: Params, start: date, end: date, rng: np.random.Generator) -> BillsResult:
    result = BillsResult()
    jitter = params["bills.variable_bill_jitter_ratio"]

    if rng.random() < params["bills.rent_probability"]:
        amount = _between(rng, params["bills.rent_monthly_sen_range"])
        day = _between(rng, params["bills.rent_day_of_month"])
        name = RENT_TEMPLATES[int(rng.integers(len(RENT_TEMPLATES)))]
        _monthly(start, end, day, name, "Rent", amount, lambda: amount, result)

    base = _between(rng, params["bills.phone_monthly_sen_range"])
    day = _between(rng, params["bills.phone_day_of_month"])
    name = PHONE_TEMPLATES[int(rng.integers(len(PHONE_TEMPLATES)))]
    _monthly(
        start,
        end,
        day,
        name,
        "Bills",
        base,
        lambda: max(int(round(base * (1 + rng.uniform(-jitter, jitter)))), 100),
        result,
    )

    if rng.random() < params["bills.subscription_probability"]:
        count = int(rng.integers(1, MAX_SUBSCRIPTIONS + 1))
        for index in rng.choice(len(SUBSCRIPTION_TEMPLATES), size=count, replace=False):
            price = _between(rng, params["bills.subscription_monthly_sen_range"])
            day = int(rng.integers(1, 29))
            _monthly(
                start,
                end,
                day,
                SUBSCRIPTION_TEMPLATES[int(index)],
                "Bills",
                price,
                lambda p=price: p,
                result,
            )

    result.events.sort(key=lambda t: (t.date, t.description))
    return result
