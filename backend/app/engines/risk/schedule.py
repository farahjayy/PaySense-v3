"""'When would this purchase not hurt?': the Second-Opinion Check's scheduler (ADR D-57).

Options are a start date (as typed, then the day after each of the next two confirmed income
dates) crossed with an instalment count (the one typed, then the others a student can pick, closest
first). Each option is judged by Engine 1's simulation with the request's seed: the chance of
running short with that plan, against the same chance without it. The first option in that fixed
order that adds at most `ADDED_MAX` and stays below the At Risk edge is suggested (ASSUMED 43); the
search stops there, so the options listed are exactly the ones tried. A student who is already At
Risk without the purchase gets no suggestion, and the caller says why.
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
    added: float
    qualifies: bool
    as_typed: bool


@dataclass(frozen=True)
class Schedule:
    without: float | None
    options: tuple[Option, ...]
    chosen: Option | None
    already_at_risk: bool


def _start_dates(request: RiskRequest, income_dates: Sequence[date]) -> list[date]:
    after = sorted({d + timedelta(days=1) for d in income_dates})
    return [request.purchase_date] + [d for d in after if d > request.purchase_date][:INCOME_DATES]


def _counts(request: RiskRequest) -> list[int]:
    current = request.num_installments
    manual = request.provider_label is not None or request.instalment_sen is not None
    if manual and request.total_payable_sen is None:
        return [current]  # each payment was typed: the count cannot change without new amounts
    return sorted({current, *OFFERED_COUNTS}, key=lambda n: (abs(n - current), n))


def _moved(request: RiskRequest, start: date) -> RiskRequest:
    delta = (start - request.purchase_date).days
    if delta == 0:
        return request
    moved = replace(request, purchase_date=start)
    if request.first_payment_date is not None:
        moved = replace(moved, first_payment_date=request.first_payment_date + timedelta(delta))
    return moved


def schedule(evaluate: Evaluate, request: RiskRequest, income_dates: Sequence[date]) -> Schedule:
    options: list[Option] = []
    without: float | None = None
    for start in _start_dates(request, income_dates):
        base = _moved(request, start)
        for count in _counts(request):
            candidate = replace(base, num_installments=count)
            judged = evaluate(candidate)
            if judged is None:
                continue
            with_purchase, without_purchase = judged
            without = without_purchase if without is None else without
            added = max(with_purchase - without_purchase, 0.0)
            option = Option(
                purchase_date=candidate.purchase_date,
                num_installments=count,
                first_payment_date=candidate.first_payment_date,
                with_purchase=with_purchase,
                added=added,
                qualifies=added <= ADDED_MAX and with_purchase < CAUTION_BELOW,
                as_typed=candidate == request,
            )
            options.append(option)
            if option.qualifies:
                return Schedule(without, tuple(options), option, without >= CAUTION_BELOW)
    already = without is not None and without >= CAUTION_BELOW
    return Schedule(without, tuple(options), None, already)
