"""The synthetic cohort (`data/synthetic/weekly_series.csv`), streamed one profile at a time."""

import csv
from collections.abc import Collection, Iterator
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from ml.engine1_eval.data import DAYS_PER_WEEK, Series

DEFAULT_PATH = Path(__file__).resolve().parents[4] / "data" / "synthetic" / "weekly_series.csv"


def _emit(index: int, weeks: list[date], spend: list[int], income: list[int]) -> Iterator[Series]:
    for kind, values in (("spend", spend), ("income", income)):
        yield Series(f"syn-{index}", kind, "synthetic", weeks[0], np.array(values, dtype=float))


def load_synthetic(
    path: Path = DEFAULT_PATH, profile_ids: Collection[int] | None = None
) -> Iterator[Series]:
    """Yield a spend and an income series per profile (optionally only the chosen profiles)."""
    last_wanted = max(profile_ids) if profile_ids else -1
    current: int | None = None
    weeks: list[date] = []
    spend: list[int] = []
    income: list[int] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            index = int(row["profile_index"])
            if profile_ids is not None and index > last_wanted:
                break  # the file is sorted by profile: nothing wanted remains
            if current is not None and index < current:
                raise ValueError(
                    f"profile {index} appears after profile {current}: file not sorted"
                )
            if index != current:
                if current is not None and weeks:
                    yield from _emit(current, weeks, spend, income)
                current, weeks, spend, income = index, [], [], []
            if profile_ids is not None and index not in profile_ids:
                continue
            week = date.fromisoformat(row["week_start"])
            if weeks and week - weeks[-1] != timedelta(days=DAYS_PER_WEEK):
                raise ValueError(f"gap in the weeks of profile {index} before {week}")
            weeks.append(week)
            spend.append(int(row["discretionary_sen"]))
            income.append(int(row["income_sen"]))
    if current is not None and weeks:
        yield from _emit(current, weeks, spend, income)
