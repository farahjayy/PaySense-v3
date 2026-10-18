"""BNPL risk check: check (stateless), confirm (create the plan and freeze the report), read back.

`check` runs the whole pipeline and stores nothing. `confirm` runs it again on the server (the
client never supplies the numbers that get frozen), saves the report, then creates the plan linked
to it; if the plan cannot be saved the report is removed, so a confirm leaves both or neither
(compensation as in ADR D-30). `GET /risk/checks/{id}` returns the stored report as it was, without
touching the live ledger.
"""

import datetime as dt
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from app.api.deps import WRITE_QUOTA, CurrentUser, DbDep, TodayDep, rate_limited
from app.api.forecast import ForecasterDep, SuspectMonthOut, daily_seed
from app.api.plans import (
    PlanIn,
    PlanOut,
    PlanPreviewOut,
    plan_create_lock,
    plan_out,
    preview_out,
    store_plan,
)
from app.api.schemas import (
    NOT_FOUND_RESPONSE,
    PROTECTED_RESPONSES,
    ApiModel,
    ErrorEnvelope,
)
from app.core.errors import api_error, not_found, unprocessable
from app.db import plans as plans_repo
from app.db import provider_limits as limits_repo
from app.db import recurring_items, risk_checks, transactions, user_settings
from app.domain import second_opinion as second
from app.domain.plan_builder import ProposalError
from app.engines.forecasting.flows import occurrences
from app.engines.forecasting.simulate import CAUTION_BELOW
from app.engines.forecasting.simulate import band as band_of
from app.engines.risk.assess import NEXT_INCOME_LOOKAHEAD_DAYS, assess
from app.engines.risk.check import CheckResult, Curve, Predictor, RiskRequest, run_check
from app.engines.risk.counterfactual import Counterfactual, describe
from app.engines.risk.explain import ExplainedFactor
from app.engines.risk.repayment import RepaymentFlag, assess_repayment
from app.engines.risk.schedule import ADDED_MAX, schedule

logger = logging.getLogger("paysense")
router = APIRouter(prefix="/risk", tags=["risk"], responses=PROTECTED_RESPONSES)
CHECK_RESPONSES: dict[int | str, dict[str, Any]] = {
    429: {"model": ErrorEnvelope, "description": "Too many requests; see Retry-After"},
    503: {
        "model": ErrorEnvelope,
        "description": "No trained model is loaded, or too many checks are running",
    },
}
CONFLICT_ENVELOPE: dict[str, Any] = {
    "model": ErrorEnvelope,
    "description": "The same purchase was just added",
}

Band = Literal["Safe", "Caution", "At Risk"]
CHECKS_PER_MINUTE = 10
# A check is 0.3-1 s of CPU and a transient memory spike, and a small host runs one worker, so how
# many run at once is capped across all users. Beyond that a request is turned away at once with a
# retry hint instead of queueing behind the others (and starving the health check).
MAX_CONCURRENT = 2
ADMISSION = threading.BoundedSemaphore(MAX_CONCURRENT)
# Purchase dates a check accepts: a little in the past (a purchase just made) to a year ahead.
DAYS_BACK = 31
DAYS_AHEAD = 366
# The same user, provider, item, date, price and instalments within this many seconds is a
# double-submit, not a second purchase.
DUPLICATE_WINDOW_SECONDS = 120
_CONFIRM_LOCKS: dict[str, threading.Lock] = {}
_CONFIRM_LOCKS_GUARD = threading.Lock()


@contextmanager
def admitted() -> Iterator[None]:
    if not ADMISSION.acquire(blocking=False):
        raise api_error(
            503,
            "risk_check_busy",
            "Several checks are running right now. Try again in a couple of seconds.",
            headers={"Retry-After": "2"},
        )
    try:
        yield
    finally:
        ADMISSION.release()


def _confirm_lock(user_id: str) -> threading.Lock:
    with _CONFIRM_LOCKS_GUARD:
        return _CONFIRM_LOCKS.setdefault(user_id, threading.Lock())


def _check_purchase_date(body: PlanIn, today: dt.date) -> None:
    low, high = today - dt.timedelta(days=DAYS_BACK), today + dt.timedelta(days=DAYS_AHEAD)
    if not low <= body.purchase_date <= high:
        raise unprocessable(
            "purchase_date_out_of_range",
            f"The purchase date must be within {DAYS_BACK} days before and {DAYS_AHEAD} days "
            "after today.",
        )


def _same_amount(plan: dict[str, Any], body: PlanIn) -> bool:
    """The money the request states matches the saved plan (whichever of the two it gave)."""
    if body.total_price_sen is not None and plan.get("total_price_sen") != body.total_price_sen:
        return False
    return body.total_payable_sen is None or plan.get("total_payable_sen") == body.total_payable_sen


def _is_duplicate(plans: list[dict[str, Any]], body: PlanIn, now: dt.datetime) -> bool:
    for plan in plans:
        created = plan.get("created_at")
        if not created:
            continue
        stamp = dt.datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=dt.UTC)
        if (now - stamp).total_seconds() > DUPLICATE_WINDOW_SECONDS:
            continue
        if (
            plan["item_name"] == body.item_name
            and plan["provider"] == body.provider
            and str(plan["purchase_date"]) == body.purchase_date.isoformat()
            and plan["num_installments"] == body.num_installments
            and _same_amount(plan, body)
        ):
            return True
    return False


# ------------------------------------------------------------------ response models
class FactorOut(ApiModel):
    feature: str
    text: str
    contribution: float = Field(ge=0, le=1)


class ChangeOut(ApiModel):
    kind: Literal["instalments", "wait", "price", "provider"]
    label: str


class ChangeSuggestionOut(ApiModel):
    status: Literal["already_safe", "found", "none_found"]
    # what the number was judged by: the model, or (for waiting, which the model cannot see) a
    # direct simulation of that exact plan
    basis: Literal["model", "simulation"] = "model"
    changes: list[ChangeOut]
    probability: float | None = Field(default=None, ge=0, le=1)
    band: Band | None = None
    request: PlanIn | None = None
    evaluated: int


class RepaymentOut(ApiModel):
    level: Literal["none", "watch", "warning"]
    overdue_count: int
    overdue_sen: int
    late_paid_count: int
    longest_miss_run: int
    reason: str


class CurveOut(ApiModel):
    months: list[str]
    cumulative_p10_sen: list[int]
    cumulative_p50_sen: list[int]
    cumulative_p90_sen: list[int]


class VersionsOut(ApiModel):
    model: str
    feature_schema_hash: str


class StackProviderOut(ApiModel):
    provider_label: str
    amount_sen: int


class StackMonthOut(ApiModel):
    month: str
    by_provider: list[StackProviderOut]
    new_plan_sen: int
    total_sen: int
    known_income_sen: int


class ExposureOut(ApiModel):
    unpaid_before_sen: int
    unpaid_after_sen: int
    providers_before: list[str]
    providers_after: list[str]
    plans_before: int
    plans_after: int
    recorded_limits_sen: int | None
    reaches_bnm_line: bool | None = Field(
        description="Recorded BNPL limits add up to RM1,500, the level at which BNM asks banks "
        "for a full affordability assessment; null when no limit is recorded"
    )
    bnm_line_sen: int = second.BNM_LIMIT_LINE_SEN


class SecondOpinionOut(ApiModel):
    """D-57: what this purchase adds, from the simulation (the quantity the label is built on)."""

    without_probability: float = Field(ge=0, le=1)
    with_probability: float = Field(ge=0, le=1)
    added_probability: float = Field(ge=0, le=1)
    already_at_risk: bool
    stack: list[StackMonthOut]
    exposure: ExposureOut


class RiskCheckOut(ApiModel):
    status: Literal["ok", "locked"]
    lock_reason: Literal["needs_four_months", "no_usable_history"] | None
    months_of_history: int
    stale_days: int | None
    unmatched_items: list[str]
    suspect_months: list[SuspectMonthOut]
    plan: PlanPreviewOut
    probability: float | None = Field(default=None, ge=0, le=1)
    band: Band | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    simulated_probability: float | None = Field(default=None, ge=0, le=1)
    # the band a direct simulation of this purchase gives; differs from `band` about 5% of the time
    simulated_band: Band | None = None
    probability_without_purchase: float | None = Field(default=None, ge=0, le=1)
    factors: list[FactorOut]
    suggestion: ChangeSuggestionOut | None = None
    repayment: RepaymentOut
    with_plan_curve: CurveOut | None = None
    without_curve: CurveOut | None = None
    versions: VersionsOut | None = None
    check_id: str | None = None
    second_opinion: SecondOpinionOut | None = None


class RiskConfirmOut(ApiModel):
    check_id: str
    check: RiskCheckOut
    plan: PlanOut


# ------------------------------------------------------------------ dependencies
def get_predictor(request: Request) -> Predictor:
    predictor = getattr(request.app.state, "predictor", None)
    if predictor is None:
        raise api_error(503, "risk_check_unavailable", "The risk check is not available right now.")
    return predictor


PredictorDep = Annotated[Predictor, Depends(get_predictor)]


# ------------------------------------------------------------------ pipeline
def _request(body: PlanIn) -> RiskRequest:
    return RiskRequest(
        provider=body.provider,
        item_name=body.item_name,
        purchase_date=body.purchase_date,
        num_installments=body.num_installments,
        total_price_sen=body.total_price_sen,
        monthly_fee_rate_pct=body.monthly_fee_rate_pct,
        first_payment_date=body.first_payment_date,
        provider_label=body.provider_label,
        instalment_sen=body.instalment_sen,
        total_payable_sen=body.total_payable_sen,
    )


def _repayment(plans: list[dict[str, Any]], today: dt.date) -> RepaymentFlag:
    return assess_repayment((i for plan in plans for i in plan["installments"]), today)


def _curve(curve: Curve | None) -> CurveOut | None:
    return None if curve is None else CurveOut(**asdict(curve))


def _suggestion(found: Counterfactual | None) -> ChangeSuggestionOut | None:
    if found is None or found.baseline_band is None:
        return None
    best = found.best
    changes = [ChangeOut(kind=c.kind, label=describe(c)) for c in (best.changes if best else ())]
    if found.baseline_band == "Safe":
        status = "already_safe"
    else:
        status = "found" if found.reaches_safe else "none_found"
    return ChangeSuggestionOut(
        status=status,
        changes=changes,
        probability=best.probability if best else None,
        band=band_of(best.probability) if best else None,  # type: ignore[arg-type]
        basis=best.basis if best else "model",  # type: ignore[arg-type]
        request=PlanIn.model_validate(asdict(best.request)) if best and best.changes else None,
        evaluated=found.evaluated,
    )


def _stored(value: float | None) -> float | None:
    """Probabilities are stored to six decimals; show exactly what would be stored."""
    return None if value is None else round(value, 6)


def _out(
    result: CheckResult,
    factors: list[ExplainedFactor],
    suggestion: Counterfactual | None,
    repayment: RepaymentFlag,
    predictor: Predictor,
) -> RiskCheckOut:
    ok = result.status == "ok"
    return RiskCheckOut(
        status=result.status,
        lock_reason=result.lock_reason,  # type: ignore[arg-type]
        months_of_history=result.months_of_history,
        stale_days=result.stale_days,
        unmatched_items=list(result.unmatched_items),
        suspect_months=[SuspectMonthOut(**vars(s)) for s in result.suspect_months],
        plan=preview_out(result.proposal),
        probability=_stored(result.probability),
        band=result.band,  # type: ignore[arg-type]
        score=result.score,
        simulated_probability=_stored(result.p_simulated),
        simulated_band=band_of(result.p_simulated) if result.p_simulated is not None else None,  # type: ignore[arg-type]
        probability_without_purchase=_stored(result.p_without),
        factors=[
            FactorOut(feature=f.feature, text=f.text, contribution=min(f.contribution, 1.0))
            for f in factors
        ],
        suggestion=_suggestion(suggestion) if ok else None,
        repayment=RepaymentOut(**asdict(repayment)),
        with_plan_curve=_curve(result.with_plan_curve),
        without_curve=_curve(result.without_curve),
        versions=VersionsOut(
            model=predictor.version, feature_schema_hash=predictor.feature_schema_hash
        )
        if ok
        else None,
    )


def _evaluate(
    body: PlanIn, user_id: str, db: Any, today: dt.date, forecaster: Any, predictor: Predictor
) -> tuple[RiskCheckOut, CheckResult]:
    rows = transactions.list_for_forecast(db, user_id, today)
    items = recurring_items.list_items(db, user_id, active_only=True)
    plans = plans_repo.list_with_instalments(db, user_id)
    limits = {r["provider"]: r["limit_sen"] for r in limits_repo.list_limits(db, user_id)}
    buffer = user_settings.get_savings_buffer(db, user_id)  # D-50: the margin starts from it
    try:
        found = assess(
            rows, items, plans, limits, _request(body), today, forecaster, predictor,
            seed=daily_seed(user_id, today), savings_buffer_sen=buffer,
        )  # fmt: skip
    except ProposalError as err:
        raise unprocessable(err.code, err.message) from err
    out = _out(found.result, found.factors, found.suggestion, _repayment(plans, today), predictor)
    opinion = _second_opinion(found.result, plans, items, limits, today)
    return out.model_copy(update={"second_opinion": opinion}), found.result


def _income_by_month(items: list[dict[str, Any]], start: dt.date, end: dt.date) -> dict[str, int]:
    """Confirmed recurring income falling in each month, from the student's own items."""
    out: dict[str, int] = {}
    for item in items:
        if item["kind"] != "income":
            continue
        for day in occurrences(item, start, end):
            key = day.strftime("%Y-%m")
            out[key] = out.get(key, 0) + int(item["amount_sen"])
    return out


def _second_opinion(
    result: CheckResult,
    plans: list[dict[str, Any]],
    items: list[dict[str, Any]],
    limits: dict[str, int | None],
    today: dt.date,
) -> SecondOpinionOut | None:
    added = second.added_probability(result.p_simulated, result.p_without)
    if result.status != "ok" or added is None or result.p_without is None:
        return None
    proposal = result.proposal
    owed = [(i.due_date, i.amount_sen) for i in proposal.instalments if not i.paid_at_checkout]
    last = max([today, *(d for d, _ in owed)])
    stack = second.stack_dues(plans, owed, _income_by_month(items, today, last), today)
    exposure = second.exposure(plans, sum(sen for _, sen in owed), proposal.provider_label, limits)
    return SecondOpinionOut(
        without_probability=_stored(result.p_without),
        with_probability=_stored(result.p_simulated),
        added_probability=_stored(added),
        already_at_risk=result.p_without >= CAUTION_BELOW,
        stack=[
            StackMonthOut(
                month=m.month,
                by_provider=[
                    StackProviderOut(provider_label=label, amount_sen=sen)
                    for label, sen in m.by_provider
                ],
                new_plan_sen=m.new_plan_sen,
                total_sen=m.total_sen,
                known_income_sen=m.known_income_sen,
            )
            for m in stack
        ],
        exposure=ExposureOut(
            unpaid_before_sen=exposure.unpaid_before_sen,
            unpaid_after_sen=exposure.unpaid_after_sen,
            providers_before=list(exposure.providers_before),
            providers_after=list(exposure.providers_after),
            plans_before=exposure.plans_before,
            plans_after=exposure.plans_after,
            recorded_limits_sen=exposure.recorded_limits_sen,
            reaches_bnm_line=exposure.reaches_bnm_line,
        ),
    )


def _frozen_row(out: RiskCheckOut, request: PlanIn, features: dict[str, float]) -> dict[str, Any]:
    if (
        out.probability is None
        or out.score is None
        or out.band is None
        or out.simulated_probability is None
        or out.versions is None
    ):
        raise ValueError("only a completed check can be frozen")
    return {
        "input": {
            "request": request.model_dump(mode="json"),
            "plan": out.plan.model_dump(mode="json"),
            "notes": {
                "months_of_history": out.months_of_history,
                "stale_days": out.stale_days,
                "unmatched_items": out.unmatched_items,
                "suspect_months": [s.model_dump(mode="json") for s in out.suspect_months],
            },
            "p_without": out.probability_without_purchase,
        },
        "features": features,
        "feature_schema_hash": out.versions.feature_schema_hash,
        "model_version": out.versions.model,
        "p": out.probability,
        "p_simulated": out.simulated_probability,
        "score": out.score,
        "label": risk_checks.LABELS[out.band],
        "factors": [f.model_dump(mode="json") for f in out.factors],
        "counterfactuals": out.suggestion.model_dump(mode="json") if out.suggestion else None,
        "repayment_flag": out.repayment.model_dump(mode="json"),
        "curves": {
            "with_plan": out.with_plan_curve.model_dump(mode="json")
            if out.with_plan_curve
            else None,
            "without": out.without_curve.model_dump(mode="json") if out.without_curve else None,
        },
    }


def _stored_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """The stored plan, with the fee and total cost added if the report was saved before they
    existed. They are the same sums the preview makes, from figures that were frozen with it."""
    if "fee_sen" in plan and "total_cost_sen" in plan:
        return plan
    return {
        **plan,
        "fee_sen": max(plan["total_payable_sen"] - plan["financed_sen"], 0),
        "total_cost_sen": plan["upfront_sen"] + plan["total_payable_sen"],
    }


def _from_row(row: dict[str, Any]) -> RiskCheckOut:
    stored = row["input"]
    notes = stored["notes"]
    curves = row["curves"] or {}
    return RiskCheckOut(
        status="ok",
        lock_reason=None,
        months_of_history=notes["months_of_history"],
        stale_days=notes["stale_days"],
        unmatched_items=notes["unmatched_items"],
        suspect_months=notes["suspect_months"],
        plan=_stored_plan(stored["plan"]),
        probability=float(row["p"]),
        band=risk_checks.BANDS[row["label"]],
        score=row["score"],
        simulated_probability=float(row["p_simulated"]),
        simulated_band=band_of(float(row["p_simulated"])),  # type: ignore[arg-type]
        probability_without_purchase=stored["p_without"],
        factors=row["factors"],
        suggestion=row["counterfactuals"],
        repayment=row["repayment_flag"],
        with_plan_curve=curves.get("with_plan"),
        without_curve=curves.get("without"),
        versions=VersionsOut(
            model=row["model_version"], feature_schema_hash=row["feature_schema_hash"]
        ),
        check_id=row["id"],
    )


# ------------------------------------------------------------------ routes
@router.post(
    "/check",
    response_model=RiskCheckOut,
    dependencies=[rate_limited("risk-check", CHECKS_PER_MINUTE, 60)],
    responses=CHECK_RESPONSES,
)
def check_risk(
    body: PlanIn,
    user: CurrentUser,
    db: DbDep,
    today: TodayDep,
    forecaster: ForecasterDep,
    predictor: PredictorDep,
) -> RiskCheckOut:
    """Stateless: nothing is stored. A ledger that is too short returns `status: locked`."""
    return check_for(body, user.id, db, today, forecaster, predictor)


def check_for(
    body: PlanIn, user_id: str, db: Any, today: dt.date, forecaster: Any, predictor: Predictor
) -> RiskCheckOut:
    """The whole stateless check: shared by the route and the assistant's `check_purchase_risk`
    tool, so both run exactly the same pipeline under the same admission cap."""
    _check_purchase_date(body, today)
    with admitted():
        out, result = _evaluate(body, user_id, db, today, forecaster, predictor)
    if result.gap is not None:  # drift watch: no user data, only the size of the disagreement
        logger.info("risk_check gap=%.3f model=%s band=%s", result.gap, predictor.version, out.band)
    return out


@router.post(
    "/confirm",
    response_model=RiskConfirmOut,
    status_code=201,
    dependencies=[WRITE_QUOTA, rate_limited("risk-check", CHECKS_PER_MINUTE, 60)],
    responses={**CHECK_RESPONSES, 409: CONFLICT_ENVELOPE},
)
def confirm_risk(
    body: PlanIn,
    user: CurrentUser,
    db: DbDep,
    today: TodayDep,
    forecaster: ForecasterDep,
    predictor: PredictorDep,
) -> RiskConfirmOut:
    """Go ahead with the purchase: freeze this check and create the plan linked to it."""
    return confirm_for(body, user.id, db, today, forecaster, predictor)


def confirm_for(
    body: PlanIn, user_id: str, db: Any, today: dt.date, forecaster: Any, predictor: Predictor
) -> RiskConfirmOut:
    """Re-evaluate on the server, freeze the report and create the plan. The one write path for a
    plan made from a risk check: the route and the assistant's confirmed `create_plan` both use
    it, with the same locks, duplicate window and admission cap."""
    _check_purchase_date(body, today)
    lock = _confirm_lock(user_id)
    if not lock.acquire(blocking=False):  # never park a server thread behind a slow confirm
        raise api_error(
            409, "confirm_in_progress", "This purchase is already being added. Wait a moment."
        )
    try:
        # one confirm at a time per user: the thread lock within this process, the database lock
        # across processes; the duplicate test reads the plans after both are held
        with admitted(), plan_create_lock(db, user_id):
            if _is_duplicate(plans_repo.list_with_instalments(db, user_id), body, _now()):
                raise api_error(
                    409,
                    "duplicate_confirm",
                    "This purchase was just added. Check your plans before adding it again.",
                )
            out, result = _evaluate(body, user_id, db, today, forecaster, predictor)
            if out.status != "ok" or result.features is None:
                raise unprocessable(
                    "forecast_locked", "There is not enough history yet to check this purchase."
                )
            return _freeze_and_create(out, result, body, user_id, db, today)
    finally:
        lock.release()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _freeze_and_create(
    out: RiskCheckOut, result: CheckResult, body: PlanIn, user_id: str, db: Any, today: dt.date
) -> RiskConfirmOut:
    """Save the report, then the plan linked to it; if the plan fails, remove the report."""
    stored = risk_checks.create(db, user_id, _frozen_row(out, body, result.features))
    try:
        plan = store_plan(
            db,
            user_id,
            body.item_name,
            result.proposal,
            risk={
                "risk_check_id": stored["id"],
                "risk_check_type": "before_purchase",
                "risk_score_at_creation": out.score,
            },
        )
    except Exception:
        try:
            risk_checks.delete(db, user_id, stored["id"])
        except Exception:
            # the original failure is what the caller must see; the leftover report is unreachable
            logger.exception("could not remove an unused risk check %s", stored["id"])
        raise
    return RiskConfirmOut(
        check_id=stored["id"],
        check=out.model_copy(update={"check_id": stored["id"]}),
        plan=plan_out(plan, today),
    )


class ScheduleOptionOut(ApiModel):
    purchase_date: dt.date
    num_installments: int
    first_payment_date: dt.date | None
    with_probability: float = Field(ge=0, le=1)
    added_probability: float = Field(ge=0, le=1)
    qualifies: bool
    as_typed: bool


class ScheduleOut(ApiModel):
    """D-57: start dates x instalment counts, judged by the simulation, tried in a fixed order
    until one adds at most `added_max` and stays below `at_risk_edge` (ASSUMED 43)."""

    status: Literal["ok", "locked"]
    without_probability: float | None
    already_at_risk: bool
    added_max: float = ADDED_MAX
    at_risk_edge: float = CAUTION_BELOW
    options: list[ScheduleOptionOut]
    chosen_index: int | None


SCHEDULES_PER_MINUTE = 5  # each one runs up to 21 simulations


@router.post(
    "/schedule",
    response_model=ScheduleOut,
    dependencies=[rate_limited("risk-schedule", SCHEDULES_PER_MINUTE, 60)],
    responses=CHECK_RESPONSES,
)
def schedule_risk(
    body: PlanIn,
    user: CurrentUser,
    db: DbDep,
    today: TodayDep,
    forecaster: ForecasterDep,
    predictor: PredictorDep,
) -> ScheduleOut:
    """Stateless: when would this purchase add little to the chance of running short?"""
    return schedule_for(body, user.id, db, today, forecaster, predictor)


def schedule_for(
    body: PlanIn, user_id: str, db: Any, today: dt.date, forecaster: Any, predictor: Predictor
) -> ScheduleOut:
    """Shared by the route and the assistant's `find_safer_timing` tool."""
    _check_purchase_date(body, today)
    rows = transactions.list_for_forecast(db, user_id, today)
    items = recurring_items.list_items(db, user_id, active_only=True)
    plans = plans_repo.list_with_instalments(db, user_id)
    limits = {r["provider"]: r["limit_sen"] for r in limits_repo.list_limits(db, user_id)}
    buffer = user_settings.get_savings_buffer(db, user_id)
    seed = daily_seed(user_id, today)
    cache: dict[Any, Any] = {}

    def evaluate(request: RiskRequest) -> tuple[float, float] | None:
        try:
            result = run_check(
                rows, items, plans, limits, request, today, forecaster, predictor,
                seed=seed, cache=cache, savings_buffer_sen=buffer,
            )  # fmt: skip
        except ProposalError:
            return None
        if result.status != "ok" or result.p_simulated is None or result.p_without is None:
            return None
        return result.p_simulated, result.p_without

    request = _request(body)
    horizon = request.purchase_date + dt.timedelta(days=NEXT_INCOME_LOOKAHEAD_DAYS)
    income_dates = sorted(
        day
        for item in items
        if item["kind"] == "income"
        for day in occurrences(item, request.purchase_date, horizon)
    )
    with admitted():
        found = schedule(evaluate, request, income_dates)
    if not found.options:
        return ScheduleOut(status="locked", without_probability=None, already_at_risk=False,
                           options=[], chosen_index=None)  # fmt: skip
    options = [
        ScheduleOptionOut(
            purchase_date=o.purchase_date,
            num_installments=o.num_installments,
            first_payment_date=o.first_payment_date,
            with_probability=_stored(o.with_purchase),
            added_probability=_stored(o.added),
            qualifies=o.qualifies,
            as_typed=o.as_typed,
        )
        for o in found.options
    ]
    chosen = found.options.index(found.chosen) if found.chosen is not None else None
    return ScheduleOut(
        status="ok",
        without_probability=_stored(found.without),
        already_at_risk=found.already_at_risk,
        options=options,
        chosen_index=chosen,
    )


@router.get("/checks/{check_id}", response_model=RiskCheckOut, responses=NOT_FOUND_RESPONSE)
def read_check(check_id: str, user: CurrentUser, db: DbDep) -> RiskCheckOut:
    row = risk_checks.get(db, user.id, check_id)
    if row is None:
        raise not_found("risk_check_not_found", "No such risk check.")
    return _from_row(row)
