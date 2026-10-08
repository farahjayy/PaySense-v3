"""The one shape every dataset is turned into: a weekly series of non-negative amounts.

Weeks run Monday to Sunday and only complete weeks are kept, so a half-observed first or last week
never looks like a spending drop. A week with nothing in it is an explicit zero. Amounts are in the
dataset's minor currency unit (sen for the synthetic cohort, pence for MoneyData, haleru for
Berka); every metric used here is scale-free, so the unit never matters.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

DAYS_PER_WEEK = 7


@dataclass(frozen=True)
class Series:
    series_id: str
    kind: str  # "spend" | "income"
    source: str  # "synthetic" | "moneydata" | "berka"
    start: date  # a Monday
    values: np.ndarray

    def __len__(self) -> int:
        return len(self.values)

    def week_starts(self) -> list[date]:
        return [self.start + timedelta(days=DAYS_PER_WEEK * i) for i in range(len(self))]


def weekly_values(
    events: Iterable[tuple[date, float]], first: date, last: date
) -> tuple[date, np.ndarray] | None:
    """Sum `(day, amount)` events into complete Monday-Sunday weeks between `first` and `last`.

    Returns `(first_monday, values)`, or None when the span holds no complete week.
    """
    monday = first + timedelta(days=(-first.weekday()) % DAYS_PER_WEEK)
    sunday = last - timedelta(days=(last.weekday() + 1) % DAYS_PER_WEEK)
    weeks = ((sunday - monday).days + 1) // DAYS_PER_WEEK
    if weeks < 1:
        return None
    values = np.zeros(weeks)
    for day, amount in events:
        index = (day - monday).days // DAYS_PER_WEEK
        if 0 <= index < weeks:
            values[index] += amount
    return monday, values


def split_profiles(count: int, seed: int, test_share: float) -> tuple[list[int], list[int]]:
    """Disjoint train / test profile indices, so a learned model never sees its test profiles."""
    order = np.random.default_rng(seed).permutation(count)
    test_size = int(round(count * test_share))
    return sorted(int(i) for i in order[test_size:]), sorted(int(i) for i in order[:test_size])
