"""The 4-month gate and "does this month look incomplete?" warnings (plan P4, task C3).

A forecast built on a ledger that is missing a month's income, or most of a month's spending, would
look precise and be wrong. The forecast is still produced when a month looks incomplete (the noisy
month stays in the residuals, so the bands widen); it is listed with a reason so the user can fix
the ledger. The thresholds below are assumptions, recorded as an ADR and tested on synthetic
personas with deliberately blanked months.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Any

from app.domain.flows import as_date, classify, month_summary

MIN_MONTHS = 4  # supervisor constraint: fewer than four months of history locks the forecast
MIN_REFERENCE_MONTHS = 3  # spending is compared with the median of at least this many months
MIN_MONTHS_WITH_INCOME = 2  # "no income" is only suspicious if income appears elsewhere...
MIN_INCOME_MONTH_SHARE = 0.5  # ...in at least half the months: a semester-funded student is not
# suspicious for having no income in most months
LOW_SPEND_FRACTION = 0.4  # ASSUMED: a month under 40% of the median month looks incomplete


@dataclass(frozen=True)
class SuspectMonth:
    month: str  # "YYYY-MM"
    reason: str  # "no_income" | "low_spend"
    detail: str


@dataclass(frozen=True)
class Completeness:
    status: str  # "ok" | "locked"
    months_of_history: int
    suspect_months: list[SuspectMonth]


def _months_with_history(rows: Iterable[Mapping[str, Any]], today: date) -> set[str]:
    return {
        as_date(row["date"]).strftime("%Y-%m")
        for row in rows
        if classify(row) != "transfer" and as_date(row["date"]) <= today
    }  # calendar months holding at least one real transaction up to today


def assess(rows: Iterable[Mapping[str, Any]], today: date) -> Completeness:
    rows = list(rows)
    months = len(_months_with_history(rows, today))
    status = "ok" if months >= MIN_MONTHS else "locked"

    current = today.strftime("%Y-%m")
    complete = [m for m in month_summary(rows) if m.month < current]
    suspects: list[SuspectMonth] = []

    income_months = [m for m in complete if m.income_sen > 0]
    regular_income = len(income_months) >= MIN_INCOME_MONTH_SHARE * len(complete)
    for m in complete:
        others_with_income = len(income_months) - (1 if m.income_sen > 0 else 0)
        if m.income_sen == 0 and others_with_income >= MIN_MONTHS_WITH_INCOME and regular_income:
            suspects.append(
                SuspectMonth(
                    m.month,
                    "no_income",
                    "No income is logged this month although it appears in other months.",
                )
            )

    suspects += _blank_months(rows, current)

    if len(complete) >= MIN_REFERENCE_MONTHS:
        typical = median(m.spend_sen for m in complete)
        for m in complete:
            if typical > 0 and m.spend_sen < LOW_SPEND_FRACTION * typical:
                suspects.append(
                    SuspectMonth(
                        m.month,
                        "low_spend",
                        "Spending this month is far below your usual; some may be missing.",
                    )
                )
    return Completeness(status, months, sorted(suspects, key=lambda s: (s.month, s.reason)))


def _blank_months(rows: list[Mapping[str, Any]], current: str) -> list[SuspectMonth]:
    """Calendar months between the first logged one and now with nothing logged at all."""
    logged = {as_date(r["date"]).strftime("%Y-%m") for r in rows if classify(r) != "transfer"}
    if not logged:
        return []
    year, month = map(int, min(logged).split("-"))
    blanks = []
    while f"{year:04d}-{month:02d}" < current:
        key = f"{year:04d}-{month:02d}"
        if key not in logged:
            blanks.append(SuspectMonth(key, "no_data", "Nothing is logged for this month."))
        year, month = year + (month == 12), month % 12 + 1
    return blanks
