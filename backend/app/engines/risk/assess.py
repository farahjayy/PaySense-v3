"""The whole risk assessment for one request: the check, the reasons, the smallest change.

The API route and the offline serving check both call this, so what is measured is what is served.
"""

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.engines.forecasting.flows import occurrences
from app.engines.forecasting.simulate import Forecaster
from app.engines.risk.check import DEFAULT_PATHS, CheckResult, Predictor, RiskRequest, run_check
from app.engines.risk.counterfactual import Counterfactual, search
from app.engines.risk.explain import ExplainedFactor, select_factors
from app.engines.risk.features import as_vector

# How far ahead a wait-for-income suggestion may look. Kept inside the 366-day purchase window
# the API accepts (`DAYS_AHEAD`), so a suggested date is never one the API would refuse.
NEXT_INCOME_LOOKAHEAD_DAYS = 300
# Candidate changes are screened with fewer simulated futures; the one shown is re-run at full
# strength, so only the search is cheaper, never the number a student sees.
SCREEN_PATHS = 300


@dataclass(frozen=True)
class Assessment:
    result: CheckResult
    factors: tuple[ExplainedFactor, ...]
    suggestion: Counterfactual | None


def next_income(items: Iterable[Mapping[str, Any]], today: dt.date) -> dt.date | None:
    """The soonest day an income item is due after today, if any. The caller passes the
    student's active items only (confirmed recurring items), so inactive ones are never used."""
    start = today + dt.timedelta(days=1)
    end = today + dt.timedelta(days=NEXT_INCOME_LOOKAHEAD_DAYS)
    upcoming = [
        days[0]
        for item in items
        if item["kind"] == "income" and (days := occurrences(item, start, end))
    ]
    return min(upcoming) if upcoming else None


def assess(
    rows: list[Mapping[str, Any]],
    items: list[Mapping[str, Any]],
    plans: list[Mapping[str, Any]],
    provider_limits: Mapping[str, int | None],
    request: RiskRequest,
    today: dt.date,
    forecaster: Forecaster,
    predictor: Predictor,
    seed: int,
    paths: int = DEFAULT_PATHS,
    savings_buffer_sen: int = 0,
) -> Assessment:
    """Raises `ProposalError` when the plan rules reject the request."""

    # candidates share one ledger: it is read once and the without-purchase simulation is reused
    cache: dict[Any, Any] = {}

    def check(candidate: RiskRequest, at: int = paths) -> CheckResult:
        return run_check(
            rows, items, plans, provider_limits, candidate, today, forecaster, predictor,
            paths=at, seed=seed, cache=cache, savings_buffer_sen=savings_buffer_sen,
        )  # fmt: skip

    result = check(request)
    if result.status != "ok" or result.features is None:
        return Assessment(result, (), None)
    # Switching provider is only suggested to one whose limit the student recorded: with no
    # record there is no cap and no utilisation, and the model would see missing information as
    # good news.
    recorded = {
        provider
        for provider, limit in provider_limits.items()
        if limit is not None and provider != request.provider
    }
    factors = tuple(
        select_factors(result.features, predictor.contributions(as_vector(result.features)))
    )
    suggestion = search(
        request,
        next_income(items, today),
        check,
        baseline=result,
        screen=lambda candidate: check(candidate, min(SCREEN_PATHS, paths)),
        switch_to=recorded,
    )
    return Assessment(result, factors, suggestion)
