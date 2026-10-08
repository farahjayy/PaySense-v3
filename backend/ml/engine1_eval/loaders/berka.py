"""Berka / PKDD'99 Czech bank: real accounts used as a multi-series benchmark only (ADR D-25).

The fixed / variable split comes from the dataset's own payment codes: standing orders for
household payments (SIPO), insurance (POJISTNE) and loan repayment (UVER) are fixed flows, which
Engine 1 places on their dates instead of forecasting, so they are left out of the variable spend
series. Interest credits (UROK) are not income. Everything else debited is variable spend and
every other credit is income.
"""

import csv
from collections import defaultdict
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from ml.engine1_eval.data import Series, weekly_values

DEFAULT_DIR = Path(__file__).resolve().parents[4] / "data" / "external" / "berka" / "raw"
FIXED_CODES = {"SIPO", "POJISTNE", "UVER"}
NOT_INCOME_CODES = {"UROK"}
CREDIT = "PRIJEM"
DEBITS = {"VYDAJ", "VYBER"}
DEFAULT_MIN_WEEKS = 52


def load_berka(
    account_path: Path = DEFAULT_DIR / "account.csv",
    trans_path: Path = DEFAULT_DIR / "trans.csv",
    min_weeks: int = DEFAULT_MIN_WEEKS,
) -> Iterator[Series]:
    with account_path.open(encoding="utf-8", newline="") as handle:
        accounts = {row["account_id"] for row in csv.DictReader(handle)}

    days: dict[str, list[date]] = defaultdict(list)
    spend: dict[str, list[tuple[date, float]]] = defaultdict(list)
    income: dict[str, list[tuple[date, float]]] = defaultdict(list)
    with trans_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            account = row["account_id"]
            if account not in accounts:
                continue
            day = date.fromisoformat(row["date"])
            amount = float(row["amount"])
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
