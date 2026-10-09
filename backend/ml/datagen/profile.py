"""One synthetic student: the output the evaluation and training code consume (plan P2, A9).

Combines the component generators (income, bills, discretionary spending, existing BNPL plans, one
proposed purchase). Each component draws from its own named stream, so profile N never depends on
how many profiles are generated and changing one component never shifts another (see rng.py).
Age and employment are not modelled as attributes: they only *drive* generation through the
persona, and are never features (PRD 3.1).
"""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from app.domain.schedule import add_months
from ml.datagen.bills import generate_bills
from ml.datagen.bnpl import BnplResult, generate_bnpl
from ml.datagen.discretionary import generate_discretionary
from ml.datagen.income import PTPTN_DESCRIPTION, generate_income
from ml.datagen.params import Params
from ml.datagen.purchase import PurchaseProposal, sample_purchase
from ml.datagen.rng import profile_rng
from ml.datagen.types import RecurringTruth, Txn

PERSONAS = ("frequent_bnpl", "budget_conscious", "irregular_income")
DEFAULT_AS_OF = date(2025, 12, 28)  # a fixed reference day, so output never depends on the clock
DAYS_PER_MONTH = 30.4375


@dataclass(frozen=True)
class StudentProfile:
    index: int
    persona: str
    start: date
    as_of: date
    transactions: tuple[Txn, ...]
    income_events: tuple[Txn, ...]  # the same objects, kept apart for the Engine 1 cohort
    discretionary_events: tuple[Txn, ...]
    recurring_truth: tuple[RecurringTruth, ...]
    bnpl: BnplResult
    purchase: PurchaseProposal
    expected_monthly_income_sen: int


def _choose_persona(params: Params, master_seed: int, index: int) -> str:
    weights = np.array([params[f"population.persona_weights.{p}"] for p in PERSONAS])
    rng = profile_rng(master_seed, index, "persona")
    return str(rng.choice(PERSONAS, p=weights / weights.sum()))


def _window_start(as_of: date, history_months: int) -> date:
    first_of_month = as_of.replace(day=1)
    return add_months(first_of_month, -(history_months - 1))


def _expected_monthly_income(events: tuple, start: date, as_of: date) -> int:
    """Typical monthly income from regular sources only. PTPTN lump sums are left out: whether one
    falls inside a short window is calendar luck, and pricing a purchase off it would make the
    purchase size depend on the month the history happens to end in."""
    span_days = (as_of - start).days + 1
    regular = sum(t.amount_sen for t in events if t.description != PTPTN_DESCRIPTION)
    return int(round(regular * DAYS_PER_MONTH / span_days))


def generate_profile(
    params: Params,
    master_seed: int,
    index: int,
    persona: str | None = None,
    history_months: int | None = None,
    as_of: date = DEFAULT_AS_OF,
) -> StudentProfile:
    if persona is not None and persona not in PERSONAS:
        raise ValueError(f"persona must be one of {PERSONAS}, got {persona!r}")
    months = int(params["history.default_months"]) if history_months is None else history_months
    if months < 1:
        raise ValueError(f"history_months must be at least 1, got {months}")
    persona = persona or _choose_persona(params, master_seed, index)
    start = _window_start(as_of, months)

    def stream(name: str) -> np.random.Generator:
        return profile_rng(master_seed, index, name)

    income = generate_income(params, persona, start, as_of, stream("income"))
    bills = generate_bills(params, start, as_of, stream("bills"))
    spending = generate_discretionary(
        params, persona, start, as_of, {t.date for t in income.events}, stream("discretionary")
    )
    bnpl = generate_bnpl(params, persona, start, as_of, stream("bnpl"))

    transactions = sorted(
        [*income.events, *bills.events, *spending, *bnpl.payments],
        key=lambda t: (t.date, t.type, t.description, t.amount_sen),
    )
    monthly_income = _expected_monthly_income(income.events, start, as_of)
    purchase = sample_purchase(params, monthly_income, as_of, bnpl, stream("purchase"))

    return StudentProfile(
        index=index,
        persona=persona,
        start=start,
        as_of=as_of,
        transactions=tuple(transactions),
        income_events=tuple(income.events),
        discretionary_events=tuple(spending),
        recurring_truth=(*income.truth, *bills.truth),
        bnpl=bnpl,
        purchase=purchase,
        expected_monthly_income_sen=monthly_income,
    )


def draw_as_of(params: Params, master_seed: int, index: int) -> date:
    """A profile's own as-of day, spread evenly over the calendar window (`calendar.*` params).

    Engine 2's labels use this so the PTPTN position, the semester and the horizon differ from
    profile to profile. It has its own stream, so no other component of the profile shifts.
    """
    start = date.fromisoformat(str(params["calendar.as_of_window_start"]))
    offset = int(
        profile_rng(master_seed, index, "as_of").integers(params["calendar.as_of_window_days"])
    )
    return start + timedelta(days=offset)


def generate_dated_profile(params: Params, master_seed: int, index: int) -> StudentProfile:
    """`generate_profile` with the profile's own drawn as-of day instead of the fixed one."""
    return generate_profile(
        params, master_seed, index, as_of=draw_as_of(params, master_seed, index)
    )
