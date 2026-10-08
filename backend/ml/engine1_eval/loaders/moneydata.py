"""MoneyData (Firat et al., EuroVis 2023): seven years of one real UK retail account, CC BY 4.0.

Spending is every debit and income every credit, except the "Savings" category (round-up sweeps
into a savings pot are not spending). Amounts are converted from pounds to pence.
"""

from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import openpyxl

from ml.engine1_eval.data import Series, weekly_values

DEFAULT_PATH = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "external"
    / "moneydata"
    / "raw"
    / "laramee26openBankTransactionData.xlsx"
)
SHEET = "Anonymized Original with Catego"
EXCLUDED_CATEGORIES = {"Savings"}
PENCE_PER_POUND = 100


def _day(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return datetime.strptime(value.strip(), "%d/%m/%Y").date()  # noqa: DTZ007
    return None


def load_moneydata(path: Path = DEFAULT_PATH) -> Iterator[Series]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    spend: list[tuple[date, float]] = []
    income: list[tuple[date, float]] = []
    days: list[date] = []
    for row in workbook[SHEET].iter_rows(min_row=2, values_only=True):
        day = _day(row[1])
        if day is None:
            continue
        days.append(day)
        if row[7] in EXCLUDED_CATEGORIES:
            continue
        if row[4]:
            spend.append((day, round(float(row[4]) * PENCE_PER_POUND)))
        if row[5]:
            income.append((day, round(float(row[5]) * PENCE_PER_POUND)))
    if not days:
        return
    for kind, events in (("spend", spend), ("income", income)):
        weekly = weekly_values(events, min(days), max(days))
        if weekly is not None:
            yield Series("moneydata-1", kind, "moneydata", weekly[0], weekly[1])
