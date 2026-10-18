"""'When would this purchase not hurt?': the Second-Opinion Check's scheduler (ADR D-57).

Options are a start date (as typed, then the day after each of the next two confirmed income
dates) crossed with an instalment count (the one typed, then the others a student can pick, closest
first). Each option is judged by Engine 1's simulation with the request's seed: the chance of
running short with that plan, against the same chance without it. The first option in that fixed
order that adds at most `ADDED_MAX` and stays below the At Risk edge is suggested (ASSUMED 43); the
search stops there, so the options listed are exactly the ones tried.

Each option is judged against its own "without" chance: the simulation runs to the end of that
option's plan, so a longer plan is judged over a longer stretch, without as well as with. A
student who is already At Risk without the purchase as typed gets no search at all (no timing can
change that), and the caller says why. A plan whose first payment date was typed keeps its date:
moving it would invent a date neither the student nor the provider gave (D-24).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta

from app.engines.forecasting.simulate import CAUTION_BELOW
from app.engines.risk.check import RiskRequest
from app.engines.risk.counterfactual import OFFERED_COUNTS

ADDED_MAX = 0.05  # ASSUMED 43: at most 5 percentage points added
INCOME_DATES = 2  # how many upcoming income dates are tried as start dates

# (chance of running short with the plan, without it), or None when the plan rules refuse it
Evaluate = Callable[[RiskRequest], tuple[float, float] | None]


@dataclass(frozen=True)
class Option:
    purchase_date: date
    num_installments: int
    first_payment_date: date | None
    with_purchase: float
    without: float  # this option's own baseline (its plan's length sets the stretch simulated)
    added: float
    qualifies: bool
    as_typed: bool


@dataclass(frozen=True)
class Schedule:
    without: float | None  # the purchase as typed
    options: tuple[Option, ...]
    chosen: Option | None
    already_at_risk: bool  # without the purchase as typed


def _start_dates(
    request: RiskRequest, income_dates: Sequence[date], latest: date | None
) -> list[date]:
    if request.first_payment_date is not None:
        return [request.purchase_date]  # a typed first payment date is never moved
    after = sorted({d + timedelta(days=1) for d in income_dates})
    later = [d for d in after if d > request.purchase_date and (latest is None or d <= latest)]
    return [request.purchase_date] + later[:INCOME_DATES]


def _counts(request: RiskRequest) -> list[int]:
    current = request.num_installments
    manual = request.provider_label is not None or request.instalment_sen is not None
    if manual and request.total_payable_sen is None:
        return [current]  # each payment was typed: the count cannot change without new amounts
    return sorted({current, *OFFERED_COUNTS}, key=lambda n: (abs(n - current), n))


def _option(candidate: RiskRequest, judged: tuple[float, float], typed: bool) -> Option:
    with_purchase, without = judged
    added = max(with_purchase - without, 0.0)
    return Option(
        purchase_date=candidate.purchase_date,
        num_installments=candidate.num_installments,
        first_payment_date=candidate.first_payment_date,
        with_purchase=with_purchase,
        without=without,
        added=added,
        qualifies=added <= ADDED_MAX and with_purchase < CAUTION_BELOW and without < CAUTION_BELOW,
        as_typed=typed,
    )


def schedule(
    evaluate: Evaluate,
    request: RiskRequest,
    income_dates: Sequence[date],
    latest: date | None = None,
) -> Schedule:
    """`latest`: the last purchase date the check accepts; later start dates are not tried."""
    typed = evaluate(request)
    if typed is None:
        return Schedule(None, (), None, False)
    first = _option(request, typed, typed=True)
    if first.qualifies or first.without >= CAUTION_BELOW:
        chosen = first if first.qualifies else None
        return Schedule(first.without, (first,), chosen, first.without >= CAUTION_BELOW)
    options = [first]
    for start in _start_dates(request, income_dates, latest):
        for count in _counts(request):
            candidate = replace(request, purchase_date=start, num_installments=count)
            if candidate == request:
                continue
            judged = evaluate(candidate)
            if judged is None:
                continue
            option = _option(candidate, judged, typed=False)
            options.append(option)
            if option.qualifies:
                return Schedule(first.without, tuple(options), option, False)
    return Schedule(first.without, tuple(options), None, False)
