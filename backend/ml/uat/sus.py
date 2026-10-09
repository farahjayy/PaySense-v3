"""System Usability Scale scoring (Brooke, 1996) and a small-sample confidence interval."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import sqrt

from scipy import stats

SUS_ITEMS = 10
LIKERT_MIN, LIKERT_MAX = 1, 5


def sus_score(responses: Sequence[int]) -> float:
    """0-100. Odd items (positively worded) score r - 1, even items (negative) score 5 - r."""
    if len(responses) != SUS_ITEMS:
        raise ValueError(f"SUS needs {SUS_ITEMS} responses, got {len(responses)}")
    if any(not LIKERT_MIN <= r <= LIKERT_MAX for r in responses):
        raise ValueError(f"SUS responses must be whole numbers {LIKERT_MIN}-{LIKERT_MAX}")
    total = sum((r - 1) if i % 2 == 0 else (5 - r) for i, r in enumerate(responses))
    return total * 2.5


@dataclass(frozen=True)
class Interval:
    n: int
    mean: float
    low: float | None
    high: float | None


def mean_interval(values: Sequence[float], level: float = 0.95) -> Interval:
    """Mean with a t-interval. With fewer than two values there is no interval, so none is given."""
    n = len(values)
    if n == 0:
        raise ValueError("no values")
    mean = sum(values) / n
    if n < 2:
        return Interval(n, mean, None, None)
    sd = sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))
    half = stats.t.ppf(0.5 + level / 2, n - 1) * sd / sqrt(n)
    return Interval(n, mean, mean - half, mean + half)
