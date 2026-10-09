"""The whole risk assessment for one request: the check, the reasons, the smallest change.

The API route and the offline serving check both call this, so what is measured is what is served.
"""

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.engines.forecasting.flows import occurrences
from app.engines.forecasting.simulate import Forecaster
from app.engines.risk.check import CheckResult, Predictor, RiskRequest, run_check
from app.engines.risk.counterfactual import Counterfactual, search
from app.engines.risk.explain import ExplainedFactor, select_factors
from app.engines.risk.features import as_vector

NEXT_INCOME_LOOKAHEAD_DAYS = 400


@dataclass(frozen=True)
class Assessment:
    result: CheckResult
    factors: list[ExplainedFactor]
    suggestion: Counterfactual | None


def next_income(items: Iterable[Mapping[str, Any]], today: dt.date) -> dt.date | None:
    """The soonest day a confirmed income item is due after today, if any."""
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
    paths: int = 1000,
) -> Assessment:
    """Raises `ProposalError` when the plan rules reject the request."""

    def check(candidate: RiskRequest) -> CheckResult:
        return run_check(
            rows, items, plans, provider_limits, candidate, today, forecaster, predictor,
            paths=paths, seed=seed,
        )  # fmt: skip

    result = check(request)
    if result.status != "ok" or result.features is None:
        return Assessment(result, [], None)
    factors = select_factors(result.features, predictor.contributions(as_vector(result.features)))
    suggestion = search(request, next_income(items, today), check, baseline=result)
    return Assessment(result, factors, suggestion)
