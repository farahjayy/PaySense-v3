"""BNPL plans: preview, create, read, rename, delete, and mark instalments paid.

`preview` and `create` run the same pure `propose_plan`, so what a person sees before confirming
is exactly what gets saved. The frontend holds no provider rule or limit arithmetic (ADR D-17).
"""

import datetime as dt
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.deps import CurrentUser, DbDep, TodayDep
from app.api.providers import ProviderKey
from app.api.schemas import NOT_FOUND_RESPONSE, PROTECTED_RESPONSES, ApiModel
from app.api.types import Sen
from app.core.errors import api_error, not_found, unprocessable
from app.db import plans as plans_repo
from app.db import provider_limits as limits_repo
from app.domain.plan_builder import PlanProposal, ProposalError, propose_plan
from app.domain.plans import enrich_plan, remaining_limit_sen
from app.domain.providers import get_provider
from app.domain.schedule import MAX_INSTALMENTS

ItemName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
PlanStatus = Literal["active", "completed", "overdue"]

router = APIRouter(prefix="/plans", tags=["plans"], responses=PROTECTED_RESPONSES)


# ------------------------------------------------------------------ request models
class PlanIn(BaseModel):
    """Either a rule-driven provider (send `total_price_sen`) or "other" (send the dates and the
    instalment amount or total payable from your own checkout)."""

    model_config = ConfigDict(extra="forbid")

    provider: ProviderKey
    item_name: ItemName
    purchase_date: dt.date
    num_installments: int = Field(ge=1, le=MAX_INSTALMENTS)
    total_price_sen: Sen | None = None
    monthly_fee_rate_pct: float = Field(default=0, ge=0, le=30)
    first_payment_date: dt.date | None = None
    provider_label: Annotated[str, StringConstraints(max_length=40)] | None = None
    instalment_sen: Sen | None = None
    total_payable_sen: Sen | None = None


class PlanPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_name: ItemName


class PayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paid_date: dt.date | None = Field(default=None, description="Defaults to today")


class BulkPayIn(PayIn):
    seqs: Annotated[list[int], Field(min_length=1, max_length=MAX_INSTALMENTS)]


# ------------------------------------------------------------------ response models
class PreviewInstalmentOut(ApiModel):
    seq: int
    due_date: dt.date
    amount_sen: int
    paid_at_checkout: bool


class PlanPreviewOut(ApiModel):
    provider: ProviderKey
    provider_label: str
    schedule_source: Literal["provider_rule", "manual"]
    total_price_sen: int
    financed_sen: int
    upfront_sen: int
    total_payable_sen: int
    cash_at_purchase_sen: int
    monthly_fee_rate_pct: float
    num_installments: int
    purchase_date: dt.date
    first_payment_date: dt.date
    limit_known: bool
    remaining_limit_sen: int | None
    installments: list[PreviewInstalmentOut]


class InstalmentOut(ApiModel):
    seq: int
    due_date: dt.date
    amount_sen: int
    is_paid: bool
    paid_date: dt.date | None


class PlanOut(ApiModel):
    id: str
    item_name: str
    provider: ProviderKey
    provider_label: str
    schedule_source: Literal["provider_rule", "manual"]
    total_price_sen: int
    financed_sen: int
    upfront_sen: int
    monthly_fee_rate_pct: float
    num_installments: int
    purchase_date: dt.date
    first_payment_date: dt.date
    status: PlanStatus
    installment_amount_sen: int
    total_payable_sen: int
    paid_count: int
    remaining_count: int
    next_due_date: dt.date | None
    risk_score_at_creation: int | None
    installments: list[InstalmentOut]


# ------------------------------------------------------------------ helpers
def _plan_missing():
    return not_found("plan_not_found", "No such plan.")


def _instalment_missing():
    return not_found("installment_not_found", "No such instalment in this plan.")


def _remaining_limit(db: Any, user_id: str, provider: str) -> int | None:
    """Remaining limit for a rule-driven provider; None if none is recorded or it does not apply."""
    if not get_provider(provider).rule_driven:
        return None
    limit = limits_repo.get_limit(db, user_id, provider)
    used = plans_repo.used_limits(db, user_id).get(provider, 0)
    return remaining_limit_sen(limit, used)


def _propose(body: PlanIn, db: Any, user_id: str) -> PlanProposal:
    try:
        return propose_plan(
            provider=body.provider,
            purchase_date=body.purchase_date,
            num_instalments=body.num_installments,
            total_price_sen=body.total_price_sen,
            monthly_fee_rate_pct=body.monthly_fee_rate_pct,
            first_payment_date=body.first_payment_date,
            provider_label=body.provider_label,
            instalment_sen=body.instalment_sen,
            total_payable_sen=body.total_payable_sen,
            remaining_limit_sen=_remaining_limit(db, user_id, body.provider),
        )
    except ProposalError as err:
        raise unprocessable(err.code, err.message) from err


def _plan_out(row: dict[str, Any], today: dt.date) -> PlanOut:
    return PlanOut.model_validate(enrich_plan(row, row["installments"], today))


def _check_paid_date(paid_date: dt.date | None, today: dt.date) -> dt.date:
    day = paid_date or today
    if day > today:
        raise unprocessable("paid_date_in_future", "A payment cannot be dated in the future.")
    return day


# ------------------------------------------------------------------ routes
@router.post("/preview", response_model=PlanPreviewOut)
def preview_plan(body: PlanIn, user: CurrentUser, db: DbDep) -> PlanPreviewOut:
    p = _propose(body, db, user.id)
    return PlanPreviewOut(
        provider=p.provider,  # type: ignore[arg-type]
        provider_label=p.provider_label,
        schedule_source=p.schedule_source,  # type: ignore[arg-type]
        total_price_sen=p.total_price_sen,
        financed_sen=p.financed_sen,
        upfront_sen=p.upfront_sen,
        total_payable_sen=p.total_payable_sen,
        cash_at_purchase_sen=p.cash_at_purchase_sen,
        monthly_fee_rate_pct=p.monthly_fee_rate_pct,
        num_installments=p.num_installments,
        purchase_date=p.purchase_date,
        first_payment_date=p.first_payment_date,
        limit_known=p.remaining_limit_sen is not None,
        remaining_limit_sen=p.remaining_limit_sen,
        installments=[
            PreviewInstalmentOut(
                seq=i.seq,
                due_date=i.due_date,
                amount_sen=i.amount_sen,
                paid_at_checkout=i.paid_at_checkout,
            )
            for i in p.instalments
        ],
    )


@router.post("", response_model=PlanOut, status_code=201)
def create_plan(body: PlanIn, user: CurrentUser, db: DbDep, today: TodayDep) -> PlanOut:
    p = _propose(body, db, user.id)
    created = plans_repo.create_plan(
        db,
        user.id,
        {
            "item_name": body.item_name,
            "provider": p.provider,
            "provider_label": p.provider_label,
            "schedule_source": p.schedule_source,
            "total_price_sen": p.total_price_sen,
            "financed_sen": p.financed_sen,
            "upfront_sen": p.upfront_sen,
            "monthly_fee_rate_pct": p.monthly_fee_rate_pct,
            "num_installments": p.num_installments,
            "purchase_date": p.purchase_date,
            "first_payment_date": p.first_payment_date,
        },
        p.instalments,
    )
    return _plan_out(created, today)


@router.get("", response_model=list[PlanOut])
def list_plans(user: CurrentUser, db: DbDep, today: TodayDep) -> list[PlanOut]:
    return [_plan_out(row, today) for row in plans_repo.list_with_instalments(db, user.id)]


@router.get("/{plan_id}", response_model=PlanOut, responses=NOT_FOUND_RESPONSE)
def get_plan(plan_id: str, user: CurrentUser, db: DbDep, today: TodayDep) -> PlanOut:
    row = plans_repo.get_with_instalments(db, user.id, plan_id)
    if row is None:
        raise _plan_missing()
    return _plan_out(row, today)


@router.patch("/{plan_id}", response_model=PlanOut, responses=NOT_FOUND_RESPONSE)
def rename_plan(
    plan_id: str, body: PlanPatch, user: CurrentUser, db: DbDep, today: TodayDep
) -> PlanOut:
    row = plans_repo.rename(db, user.id, plan_id, body.item_name)
    if row is None:
        raise _plan_missing()
    return _plan_out(row, today)


@router.delete("/{plan_id}", status_code=204, responses=NOT_FOUND_RESPONSE)
def delete_plan(plan_id: str, user: CurrentUser, db: DbDep, keep_payments: bool = True) -> Response:
    """Delete a plan. Payments it logged are kept by default (unlinked); pass
    `keep_payments=false` to delete them too."""
    if not plans_repo.delete(db, user.id, plan_id, keep_payments=keep_payments):
        raise _plan_missing()
    return Response(status_code=204)


@router.post(
    "/{plan_id}/installments/{seq}/pay",
    response_model=InstalmentOut,
    responses={**NOT_FOUND_RESPONSE, 409: {"description": "Already paid, or changed concurrently"}},
)
def pay_installment(
    plan_id: str,
    seq: Annotated[int, Field(ge=1, le=MAX_INSTALMENTS)],
    user: CurrentUser,
    db: DbDep,
    today: TodayDep,
    body: PayIn | None = None,
) -> InstalmentOut:
    day = _check_paid_date(body.paid_date if body else None, today)
    try:
        paid = plans_repo.mark_paid(db, user.id, plan_id, seq, day)
    except plans_repo.AlreadyPaidError as err:
        raise api_error(409, "already_paid", "That instalment is already marked paid.") from err
    except plans_repo.PlanConflictError as err:
        raise api_error(
            409, "plan_conflict", "That instalment just changed. Refresh and retry."
        ) from err
    if paid is None:
        if plans_repo.get_with_instalments(db, user.id, plan_id) is None:
            raise _plan_missing()
        raise _instalment_missing()
    return InstalmentOut.model_validate(paid)


@router.post(
    "/{plan_id}/pay",
    response_model=list[InstalmentOut],
    responses={**NOT_FOUND_RESPONSE, 409: {"description": "An instalment is already paid"}},
)
def pay_installments(
    plan_id: str, body: BulkPayIn, user: CurrentUser, db: DbDep, today: TodayDep
) -> list[InstalmentOut]:
    """Mark several instalments paid at once. Everything is checked before anything is paid."""
    day = _check_paid_date(body.paid_date, today)
    if plans_repo.get_with_instalments(db, user.id, plan_id) is None:
        raise _plan_missing()
    try:
        paid = plans_repo.mark_paid_many(db, user.id, plan_id, body.seqs, day)
    except plans_repo.AlreadyPaidError as err:
        raise api_error(409, "already_paid", str(err)) from err
    except plans_repo.PlanConflictError as err:
        raise api_error(
            409, "plan_conflict", "An instalment just changed. Refresh and retry."
        ) from err
    except ValueError as err:
        raise _instalment_missing() from err
    return [InstalmentOut.model_validate(row) for row in paid]
