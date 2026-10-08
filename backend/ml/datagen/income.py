"""Income process (plan P2, A4): allowance, PTPTN lump sums, part-time pay and gig income.

The three persona shapes are built from these pieces (parameters and their provenance are in
`params.yaml`). Alongside the dated events the generator returns the *ground truth* recurring
items, which P4 uses to score recurring-income detection.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from ml.datagen.calendar import day_in_month, iter_month_starts, iter_weeks
from ml.datagen.params import Params
from ml.datagen.types import RecurringTruth, Txn

ALLOWANCE_TEMPLATES = (
    "Monthly allowance from Parents",
    "Duit belanja bulanan",
    "Allowance - Mak",
    "Allowance from Ayah",
)
PTPTN_DESCRIPTION = "PTPTN disbursement"
# Words are chosen so the importer's first-match categoriser reads them as Salary ("cafe" would be
# read as Food, which sits earlier in its keyword order).
PARTTIME_TEMPLATES = ("Salary - part time", "Gaji part time", "Salary - weekend job")
GIG_TEMPLATES = ("Freelance payout", "Gig payout", "Event crew payout", "Delivery payout")
MIN_SEN = 100  # nothing below RM1


@dataclass
class IncomeResult:
    events: list[Txn] = field(default_factory=list)
    truth: list[RecurringTruth] = field(default_factory=list)


def _sen(value: float) -> int:
    return max(int(round(value)), MIN_SEN)


def _lognormal(rng: np.random.Generator, median: float, sigma: float) -> float:
    return float(median * np.exp(rng.normal(0.0, sigma)))


def _in_window(day: date, start: date, end: date) -> bool:
    return start <= day <= end


def _allowance(params: Params, persona: str, start: date, end: date, rng, out: IncomeResult):
    if rng.random() >= params[f"income.allowance_probability.{persona}"]:
        return
    amount = _sen(
        _lognormal(
            rng, params[f"income.allowance_median_sen.{persona}"], params["income.allowance_sigma"]
        )
    )
    low, high = params["income.allowance_day_of_month"]
    day = int(rng.integers(low, high + 1))
    label = ALLOWANCE_TEMPLATES[int(rng.integers(len(ALLOWANCE_TEMPLATES)))]
    first = None
    for month in iter_month_starts(start, end):
        when = day_in_month(month.year, month.month, day)
        if _in_window(when, start, end):
            out.events.append(Txn(when, amount, "income", "Allowance", label))
            first = first or when
    if first:
        out.truth.append(RecurringTruth(label, "income", amount, "monthly", first))


def _ptptn(params: Params, persona: str, start: date, end: date, rng, out: IncomeResult):
    if rng.random() >= params[f"income.ptptn_probability.{persona}"]:
        return
    annual = int(rng.choice(params["income.ptptn_annual_sen"]))
    count = params["income.ptptn_disbursements_per_year"]
    months = params["income.ptptn_months"][:count]
    lump = annual // count
    first = None
    for year in range(start.year, end.year + 1):
        for month in months:
            when = day_in_month(year, month, params["income.ptptn_pay_day"])
            if _in_window(when, start, end):
                out.events.append(Txn(when, lump, "income", "Allowance", PTPTN_DESCRIPTION))
                first = first or when
    if first:
        out.truth.append(RecurringTruth(PTPTN_DESCRIPTION, "income", lump, "semester", first))


def _part_time(params: Params, persona: str, start: date, end: date, rng, out: IncomeResult):
    if rng.random() >= params[f"income.parttime_probability.{persona}"]:
        return
    level = _lognormal(
        rng, params["income.parttime_monthly_median_sen"], params["income.parttime_sigma"]
    )
    jitter = params["income.parttime_monthly_jitter"]
    label = PARTTIME_TEMPLATES[int(rng.integers(len(PARTTIME_TEMPLATES)))]
    first = None
    for month in iter_month_starts(start, end):
        when = day_in_month(month.year, month.month, params["income.parttime_pay_day"])
        if _in_window(when, start, end):
            pay = _sen(level * (1 + rng.uniform(-jitter, jitter)))
            out.events.append(Txn(when, pay, "income", "Salary", label))
            first = first or when
    if first:
        out.truth.append(RecurringTruth(label, "income", _sen(level), "monthly", first))


def _gig(params: Params, start: date, end: date, rng, out: IncomeResult):
    dry_months = {
        (m.year, m.month)
        for m in iter_month_starts(start, end)
        if rng.random() < params["income.gig_dry_spell_probability_per_month"]
    }
    for monday in iter_weeks(start, end):
        mean = params["income.gig_jobs_per_week_mean"]
        if (monday.year, monday.month) in dry_months:
            mean *= params["income.gig_dry_spell_job_multiplier"]
        for _ in range(int(rng.poisson(mean))):
            when = monday + timedelta(days=int(rng.integers(0, 7)))
            if _in_window(when, start, end):
                pay = _sen(
                    _lognormal(
                        rng, params["income.gig_pay_median_sen"], params["income.gig_pay_sigma"]
                    )
                )
                label = GIG_TEMPLATES[int(rng.integers(len(GIG_TEMPLATES)))]
                out.events.append(Txn(when, pay, "income", "Gig", label))


def generate_income(
    params: Params, persona: str, start: date, end: date, rng: np.random.Generator
) -> IncomeResult:
    """Dated income events (sorted by date) and the recurring items they follow."""
    result = IncomeResult()
    _allowance(params, persona, start, end, rng, result)
    _ptptn(params, persona, start, end, rng, result)
    _part_time(params, persona, start, end, rng, result)
    if persona == "irregular_income":
        _gig(params, start, end, rng, result)
    result.events.sort(key=lambda t: (t.date, t.description))
    return result
