"""The BNPL risk check: one purchase, one provider, one answer (plan P6, task E2).

Pipeline: the provider's own rules turn the request into a schedule (capped by the recorded limit,
D-28) -> the forecast is simulated with and without that schedule -> `features.py` turns both into
the 16 model inputs -> the trained model gives the shown probability. The simulated probability
for the same purchase (the exact training label, D-07) is returned beside it and their gap is
meant to be logged, so a model that drifts from its own simulation shows up.

A ledger the forecast refuses (too little history) returns a refusal, never a number.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Protocol

from app.domain.plan_builder import PlanProposal, propose_plan
from app.domain.plans import remaining_limit_sen, used_limit_sen
from app.domain.providers import get_provider
from app.engines.forecasting.service import Forecast, SuspectMonth, build_forecast
from app.engines.forecasting.simulate import Forecaster, Simulation, band, health_score
from app.engines.forecasting.summary import build_feature_inputs
from app.engines.risk.features import as_vector, compute_features


class Predictor(Protocol):
    """The trained, calibrated model: 16 feature values in, a probability out."""

    version: str

    def predict(self, vector: Sequence[float]) -> float: ...


@dataclass(frozen=True)
class RiskRequest:
    """What the student typed. The same fields the plan screen collects."""

    provider: str
    item_name: str
    purchase_date: date
    num_installments: int
    total_price_sen: int | None = None
    monthly_fee_rate_pct: float = 0.0
    first_payment_date: date | None = None
    provider_label: str | None = None
    instalment_sen: int | None = None
    total_payable_sen: int | None = None


@dataclass(frozen=True)
class Curve:
    """Cumulative margin by month-end, for the with-and-without chart."""

    months: tuple[str, ...]
    cumulative_p10_sen: tuple[int, ...]
    cumulative_p50_sen: tuple[int, ...]
    cumulative_p90_sen: tuple[int, ...]


@dataclass(frozen=True)
class CheckResult:
    status: Literal["ok", "locked"]
    lock_reason: str | None
    months_of_history: int
    stale_days: int | None
    unmatched_items: tuple[str, ...]
    suspect_months: tuple[SuspectMonth, ...]
    proposal: PlanProposal
    probability: float | None = None
    band: str | None = None
    score: int | None = None
    p_simulated: float | None = None
    p_without: float | None = None
    features: dict[str, float] | None = None
    with_plan_curve: Curve | None = None
    without_curve: Curve | None = None
    predictor_version: str | None = None

    @property
    def gap(self) -> float | None:
        """Shown probability minus the simulated one for the same purchase."""
        if self.probability is None or self.p_simulated is None:
            return None
        return self.probability - self.p_simulated


def remaining_limit(
    provider: str, provider_limits: Mapping[str, int | None], plans: Iterable[Mapping[str, Any]]
) -> int | None:
    """What is left of the recorded limit for a rule-driven provider; None when none applies."""
    if not get_provider(provider).rule_driven:
        return None
    unpaid = [i for p in plans if p.get("provider") == provider for i in p["installments"]]
    return remaining_limit_sen(provider_limits.get(provider), used_limit_sen(unpaid))


def _curve(sim: Simulation) -> Curve:
    return Curve(
        months=tuple(sim.months),
        cumulative_p10_sen=tuple(int(v) for v in sim.cumulative_margin_p10_sen),
        cumulative_p50_sen=tuple(int(v) for v in sim.cumulative_margin_p50_sen),
        cumulative_p90_sen=tuple(int(v) for v in sim.cumulative_margin_p90_sen),
    )


def _refusal(forecast: Forecast, proposal: PlanProposal) -> CheckResult:
    return CheckResult(
        status="locked",
        lock_reason=forecast.lock_reason,
        months_of_history=forecast.months_of_history,
        stale_days=forecast.stale_days,
        unmatched_items=tuple(forecast.unmatched_items),
        suspect_months=tuple(forecast.suspect_months),
        proposal=proposal,
    )


def run_check(
    rows: Iterable[Mapping[str, Any]],
    items: Iterable[Mapping[str, Any]],
    plans: Iterable[Mapping[str, Any]],
    provider_limits: Mapping[str, int | None],
    request: RiskRequest,
    today: date,
    forecaster: Forecaster,
    predictor: Predictor,
    paths: int = 1000,
    seed: int = 0,
) -> CheckResult:
    """Raises `ProposalError` when the plan rules reject the request (the API maps it to 422)."""
    rows, items, plans = list(rows), list(items), list(plans)
    proposal = propose_plan(
        provider=request.provider,
        purchase_date=request.purchase_date,
        num_instalments=request.num_installments,
        total_price_sen=request.total_price_sen,
        monthly_fee_rate_pct=request.monthly_fee_rate_pct,
        first_payment_date=request.first_payment_date,
        provider_label=request.provider_label,
        instalment_sen=request.instalment_sen,
        total_payable_sen=request.total_payable_sen,
        remaining_limit_sen=remaining_limit(request.provider, provider_limits, plans),
    )
    built = build_feature_inputs(
        rows, items, plans, proposal, provider_limits, today, forecaster, seed=seed, paths=paths
    )
    if built is None:
        refusal = build_forecast(
            rows=rows, items=items, plans=plans, today=today, forecaster=forecaster, seed=seed
        )
        return _refusal(refusal, proposal)

    features = compute_features(built.inputs)
    probability = float(predictor.predict(as_vector(features)))
    shown = built.without
    return CheckResult(
        status="ok",
        lock_reason=None,
        months_of_history=shown.months_of_history,
        stale_days=shown.stale_days,
        unmatched_items=tuple(shown.unmatched_items),
        suspect_months=tuple(shown.suspect_months),
        proposal=proposal,
        probability=probability,
        band=band(probability),
        score=health_score(probability),
        p_simulated=built.p_with,
        p_without=built.p_without,
        features=features,
        with_plan_curve=_curve(built.with_plan.simulation),
        without_curve=_curve(built.without.simulation),
        predictor_version=predictor.version,
    )
