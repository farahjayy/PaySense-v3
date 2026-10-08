"""Berka / PKDD'99 Czech bank: real accounts used as a multi-series benchmark only (ADR D-25).

The fixed / variable split comes from the dataset's own payment codes: standing orders for
household payments (SIPO), insurance (POJISTNE) and loan repayment (UVER) are fixed flows, which
Engine 1 places on their dates instead of forecasting, so they are left out of the variable spend
series. Interest credits (UROK) are not income. Everything else debited is variable spend and
every other credit is income.

The transaction file has about a million rows, so accounts are chosen from a cheap first pass
(first and last date per account) and only the chosen accounts' rows are kept in the second.
"""

import csv
import math
from collections import defaultdict
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import numpy as np

from ml.engine1_eval.data import DAYS_PER_WEEK, Series, weekly_values

DEFAULT_DIR = Path(__file__).resolve().parents[4] / "data" / "external" / "berka" / "raw"
FIXED_CODES = {"SIPO", "POJISTNE", "UVER"}
NOT_INCOME_CODES = {"UROK"}
CREDIT = "PRIJEM"
DEBITS = {"VYDAJ", "VYBER"}
DEFAULT_MIN_WEEKS = 52


def _rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def _spans(trans_path: Path, accounts: set[str]) -> dict[str, tuple[date, date]]:
    first: dict[str, date] = {}
    last: dict[str, date] = {}
    for row in _rows(trans_path):
        account = row["account_id"]
        if account not in accounts:
            continue
        day = date.fromisoformat(row["date"])
        first[account] = min(day, first.get(account, day))
        last[account] = max(day, last.get(account, day))
    return {a: (first[a], last[a]) for a in first}


def _choose(
    spans: dict[str, tuple[date, date]], min_weeks: int, sample: tuple[int, int] | None
) -> list[str]:
    eligible = sorted(
        (
            a
            for a, (start, end) in spans.items()
            if ((end - start).days + 1) // DAYS_PER_WEEK >= min_weeks  # an upper bound
        ),
        key=int,
    )
    if sample is None:
        return eligible
    count, seed = sample
    order = np.random.default_rng(seed).permutation(len(eligible))[:count]
    return [eligible[i] for i in sorted(order)]


def load_berka(
    account_path: Path = DEFAULT_DIR / "account.csv",
    trans_path: Path = DEFAULT_DIR / "trans.csv",
    min_weeks: int = DEFAULT_MIN_WEEKS,
    sample: tuple[int, int] | None = None,
) -> Iterator[Series]:
    """Spend and income series per account; `sample=(count, seed)` keeps a seeded subset."""
    accounts = {row["account_id"] for row in _rows(account_path)}
    chosen = set(_choose(_spans(trans_path, accounts), min_weeks, sample))

    days: dict[str, list[date]] = defaultdict(list)
    spend: dict[str, list[tuple[date, float]]] = defaultdict(list)
    income: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for row in _rows(trans_path):
        account = row["account_id"]
        if account not in chosen:
            continue
        amount = float(row["amount"])
        if not math.isfinite(amount) or amount < 0:
            raise ValueError(f"unusable amount {row['amount']!r} in transaction {row['trans_id']}")
        day = date.fromisoformat(row["date"])
        symbol = row["k_symbol"]
        days[account].append(day)
        if row["type"] == CREDIT and symbol not in NOT_INCOME_CODES:
            income[account].append((day, amount))
        elif row["type"] in DEBITS and symbol not in FIXED_CODES:
            spend[account].append((day, amount))

    for account in sorted(days, key=int):
        for kind, events in (("spend", spend[account]), ("income", income[account])):
            weekly = weekly_values(events, min(days[account]), max(days[account]))
            if weekly is not None and len(weekly[1]) >= min_weeks:
                yield Series(f"berka-{account}", kind, "berka", weekly[0], weekly[1])
