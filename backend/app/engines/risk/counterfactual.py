"""'What would make this safer?': an exact search over a small grid of things a student can do.

Levers (PRD 3.1, ADR D-12): more instalments, buying after the next income, a lower price, another
provider. Every candidate goes through the whole pipeline (plan rules -> simulations -> features ->
model), so the answer is what the model actually says about that plan, not a rule of thumb.

"Smallest" is a fixed, written-down ordering of effort, not a guess about taste: one change before
two; within that, cheaper first by the `*_EFFORT` numbers below. The first candidate in that order
that reaches Safe is returned. If none does within `MAX_EVALUATIONS`, the best one found is returned
with `reaches_safe=False`, and the caller says plainly that nothing in the grid gets there.
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass, replace
from datetime import date
from itertools import combinations
from typing import Any

from app.domain.plan_builder import ProposalError
from app.domain.providers import PROVIDERS, get_provider
from app.engines.forecasting.simulate import SAFE_BELOW, band
from app.engines.risk.check import RiskRequest

# Counts a student can realistically pick at checkout. ASSUMED (the providers' own menus are not
# published in a form the app can read); only counts above the current one are tried.
OFFERED_COUNTS: tuple[int, ...] = (2, 3, 4, 6, 9, 12)
PRICE_CUTS_PCT: tuple[int, ...] = (10, 25, 50)
MAX_EVALUATIONS = 60

# Relative effort of each change, used only to order the search.
COUNT_STEP_EFFORT = 1.0  # per step up the OFFERED_COUNTS list
WAIT_EFFORT = 2.0
PRICE_BASE_EFFORT = 3.0  # plus the cut percentage / 25
PROVIDER_EFFORT = 6.0

Evaluate = Callable[[RiskRequest], Any]


@dataclass(frozen=True)
class Change:
    kind: str  # "instalments" | "wait" | "price" | "provider"
    value: Any


@dataclass(frozen=True)
class Candidate:
    changes: tuple[Change, ...]
    request: RiskRequest
    effort: float


@dataclass(frozen=True)
class Outcome:
    changes: tuple[Change, ...]
    request: RiskRequest
    probability: float
    basis: str = "model"  # "simulation" when the model cannot see what the change does


@dataclass(frozen=True)
class Counterfactual:
    baseline_band: str | None
    baseline_probability: float | None
    reaches_safe: bool
    best: Outcome | None
    evaluated: int


def _is_manual(request: RiskRequest) -> bool:
    return not get_provider(request.provider).rule_driven


def _single_changes(
    request: RiskRequest, next_income: date | None, switch_to: Collection[str] | None
) -> list[Candidate]:
    out: list[Candidate] = []
    manual = _is_manual(request)

    # more instalments: for a manual plan only when the total (not each payment) was entered
    if not manual or request.total_payable_sen is not None:
        current = request.num_installments
        steps = [n for n in OFFERED_COUNTS if n > current]
        for rank, count in enumerate(steps, start=1):
            out.append(
                Candidate(
                    (Change("instalments", count),),
                    replace(request, num_installments=count),
                    COUNT_STEP_EFFORT * rank,
                )
            )

    # buy after the next income: the whole schedule moves by the same number of days
    if next_income is not None:
        target = date.fromordinal(next_income.toordinal() + 1)
        delta = (target - request.purchase_date).days
        if delta > 0:
            moved = replace(request, purchase_date=target)
            if request.first_payment_date is not None:
                shifted = date.fromordinal(request.first_payment_date.toordinal() + delta)
                moved = replace(moved, first_payment_date=shifted)
            out.append(Candidate((Change("wait", target),), moved, WAIT_EFFORT))

    # a lower price (only when a price was entered, i.e. a rule-driven provider)
    if request.total_price_sen is not None:
        for pct in PRICE_CUTS_PCT:
            cut = request.total_price_sen * (100 - pct) // 100
            if cut > 0:
                out.append(
                    Candidate(
                        (Change("price", cut),),
                        replace(request, total_price_sen=cut),
                        PRICE_BASE_EFFORT + pct / 25,
                    )
                )

    # another rule-driven provider, same price and count, at that provider's own fee rule
    if not manual:
        for key, config in PROVIDERS.items():
            allowed = switch_to is None or key in switch_to
            if config.rule_driven and key != request.provider and allowed:
                fee = request.monthly_fee_rate_pct if config.monthly_fee_applies else 0.0
                out.append(
                    Candidate(
                        (Change("provider", key),),
                        replace(request, provider=key, monthly_fee_rate_pct=fee),
                        PROVIDER_EFFORT,
                    )
                )
    return out


def _combine(a: Candidate, b: Candidate) -> Candidate | None:
    """Two changes of different kinds applied together, or None if they cannot be."""
    if {c.kind for c in a.changes} & {c.kind for c in b.changes}:
        return None
    request = a.request
    for change in b.changes:
        if change.kind == "instalments":
            request = replace(request, num_installments=b.request.num_installments)
        elif change.kind == "wait":
            request = replace(
                request,
                purchase_date=b.request.purchase_date,
                first_payment_date=b.request.first_payment_date,
            )
        elif change.kind == "price":
            request = replace(request, total_price_sen=b.request.total_price_sen)
        elif change.kind == "provider":
            request = replace(
                request,
                provider=b.request.provider,
                monthly_fee_rate_pct=b.request.monthly_fee_rate_pct,
            )
    return Candidate(a.changes + b.changes, request, a.effort + b.effort)


def candidates(
    request: RiskRequest,
    next_income: date | None,
    switch_to: Collection[str] | None = None,
) -> list[Candidate]:
    """Every candidate to try, in the order to try them, at most `MAX_EVALUATIONS`.

    `switch_to` limits which other providers are tried (None: any rule-driven one). The app only
    knows a student's room with a provider whose limit they recorded, so only those are offered.
    """
    singles = sorted(_single_changes(request, next_income, switch_to), key=lambda c: c.effort)
    pairs = [merged for a, b in combinations(singles, 2) if (merged := _combine(a, b)) is not None]
    pairs.sort(key=lambda c: c.effort)
    seen: set[str] = set()
    ordered: list[Candidate] = []
    for candidate in [*singles, *pairs]:
        key = repr(candidate.request)
        if key in seen or candidate.request == request:
            continue
        seen.add(key)
        ordered.append(candidate)
    return ordered[:MAX_EVALUATIONS]


SCREEN_MARGIN = 0.02  # a screened result this close to the Safe edge is confirmed at full strength
# At most this many near-edge candidates are confirmed during the search, so a request sitting on
# the edge cannot cost sixty full-strength runs; the best one is still confirmed at the end.
MAX_CONFIRMATIONS = 6


def _judged(result: Any, candidate: Candidate) -> tuple[float, str]:
    """The number a candidate is judged by, and where it came from.

    The model cannot see when a purchase happens (none of its features involve timing), so waiting
    is judged by the direct simulation of that exact plan, which does. Everything else is judged by
    the model, which is what the student is shown.
    """
    if any(change.kind == "wait" for change in candidate.changes):
        simulated = getattr(result, "p_simulated", None)
        if simulated is not None:
            return float(simulated), "simulation"
    return float(result.probability), "model"


def search(
    request: RiskRequest,
    next_income: date | None,
    evaluate: Evaluate,
    baseline: Any = None,
    screen: Evaluate | None = None,
    switch_to: Collection[str] | None = None,
) -> Counterfactual:
    """Run the grid through `evaluate(request) -> result with .status and .probability`.

    `evaluate` may raise `ProposalError` for a candidate the plan rules reject; that candidate is
    skipped. A locked ledger (no probability) yields no suggestion at all. Pass the check already
    run for `request` as `baseline` to avoid running it twice.

    `screen` is a cheaper version of `evaluate` (fewer simulated futures). Candidates are screened
    with it, and only one that screens Safe (or within `SCREEN_MARGIN` of it), or the best one when
    none does, is run through `evaluate`: what is returned is always an `evaluate` result.

    A best effort that is no better than doing nothing is not offered.
    """
    base = baseline if baseline is not None else evaluate(request)
    if base.status != "ok" or base.probability is None:
        return Counterfactual(None, None, False, None, 0)
    start = band(base.probability)
    if start == "Safe":
        return Counterfactual(
            start, base.probability, True, Outcome((), request, base.probability), 0
        )

    probe = screen or evaluate
    tried = 0
    confirmations = 0
    best: Outcome | None = None
    for candidate in candidates(request, next_income, switch_to):
        try:
            result = probe(candidate.request)
        except ProposalError:
            continue
        tried += 1
        if result.status != "ok" or result.probability is None:
            continue
        value, basis = _judged(result, candidate)
        outcome = Outcome(candidate.changes, candidate.request, value, basis)
        near_edge = value < SAFE_BELOW + (SCREEN_MARGIN if screen is not None else 0)
        if near_edge and (screen is None or confirmations < MAX_CONFIRMATIONS):
            confirmed = outcome
            if screen is not None:
                confirmations += 1
                confirmed = _confirm(outcome, candidate, evaluate)
            if confirmed is not None and band(confirmed.probability) == "Safe":
                return Counterfactual(start, base.probability, True, confirmed, tried)
            outcome = confirmed or outcome
        if best is None or outcome.probability < best.probability:
            best = outcome

    if screen is not None and best is not None:
        matching = next(
            c for c in candidates(request, next_income, switch_to) if c.request == best.request
        )
        best = _confirm(best, matching, evaluate) or best
        if band(best.probability) == "Safe":
            return Counterfactual(start, base.probability, True, best, tried)
    if best is not None and best.probability >= _same_basis(base, best):
        best = None
    return Counterfactual(start, base.probability, False, best, tried)


def _same_basis(base: Any, outcome: Outcome) -> float:
    """The unchanged purchase measured the way `outcome` was, so the two can be compared."""
    if outcome.basis == "simulation":
        simulated = getattr(base, "p_simulated", None)
        if simulated is not None:
            return float(simulated)
    return float(base.probability)


def _confirm(outcome: Outcome, candidate: Candidate, evaluate: Evaluate) -> Outcome | None:
    """The same candidate at full strength, or None if it cannot be evaluated."""
    try:
        result = evaluate(outcome.request)
    except ProposalError:
        return None
    if result.status != "ok" or result.probability is None:
        return None
    value, basis = _judged(result, candidate)
    return Outcome(outcome.changes, outcome.request, value, basis)


_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
_PROVIDER_NAMES = {"spaylater": "SPayLater", "tiktok_paylater": "TikTok PayLater", "atome": "Atome"}


def describe(change: Change) -> str:
    """One plain sentence for a change; every number in it is the change's own value."""
    if change.kind == "instalments":
        return f"Spread it over {change.value} instalments"
    if change.kind == "wait":
        day: date = change.value
        return f"Buy it on {day.day} {_MONTHS[day.month - 1]} {day.year}, after your next income"
    if change.kind == "price":
        return f"Choose something priced at about RM {round(change.value / 100):,}"
    if change.kind == "provider":
        return f"Use {_PROVIDER_NAMES.get(change.value, change.value)} instead"
    raise ValueError(f"unknown change kind {change.kind!r}")
