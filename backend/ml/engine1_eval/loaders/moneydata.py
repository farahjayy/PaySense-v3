"""MoneyData (Firat et al., EuroVis 2023): seven years of one real UK retail account, CC BY 4.0.

Spending is every debit and income every credit, except the "Savings" category (round-up sweeps
into a savings pot are not spending). Unlike the Berka series, fixed bills are NOT separated out:
the dataset has no fixed/variable code, so this spend series includes rent-like payments.
Amounts are converted from pounds to pence.

The file is third-party data: its SHA-256 is checked before it is parsed.
"""

import hashlib
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
EXPECTED_SHA256 = "716eaf9ad4a3cf60dc9c9c8a20ed9a917c545a1b5f139f40ed91d2104faa3ff7"
SHEET = "Anonymized Original with Catego"
EXCLUDED_CATEGORIES = {"Savings"}
PENCE_PER_POUND = 100
COLUMNS = 10
DATE_COLUMN, DEBIT_COLUMN, CREDIT_COLUMN, CATEGORY_COLUMN = 1, 4, 5, 7


def _day(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return datetime.strptime(value.strip(), "%d/%m/%Y").date()  # noqa: DTZ007
    return None  # blank trailing rows; anything else would be a different format


def load_moneydata(
    path: Path = DEFAULT_PATH, expected_sha256: str | None = EXPECTED_SHA256
) -> Iterator[Series]:
    if expected_sha256 is not None:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected_sha256:
            raise ValueError(f"{path.name} does not match the published checksum ({digest})")
    spend: list[tuple[date, float]] = []
    income: list[tuple[date, float]] = []
    days: list[date] = []
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for raw in workbook[SHEET].iter_rows(min_row=2, values_only=True):
            row = (*raw, *([None] * COLUMNS))  # read-only mode may trim trailing empty cells
            day = _day(row[DATE_COLUMN])
            if day is None:
                continue
            days.append(day)
            if row[CATEGORY_COLUMN] in EXCLUDED_CATEGORIES:
                continue
            if row[DEBIT_COLUMN]:
                spend.append((day, round(float(row[DEBIT_COLUMN]) * PENCE_PER_POUND)))
            if row[CREDIT_COLUMN]:
                income.append((day, round(float(row[CREDIT_COLUMN]) * PENCE_PER_POUND)))
    finally:
        workbook.close()
    if not days:
        return
    for kind, events in (("spend", spend), ("income", income)):
        weekly = weekly_values(events, min(days), max(days))
        if weekly is not None:
            yield Series("moneydata-1", kind, "moneydata", weekly[0], weekly[1])
