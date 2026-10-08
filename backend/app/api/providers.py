"""Provider rules, served from the backend so the frontend never mirrors them (ADR D-17)."""

from typing import Literal

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.api.schemas import PROTECTED_RESPONSES, ApiModel
from app.domain.providers import PROVIDERS

ProviderKey = Literal["spaylater", "tiktok_paylater", "atome", "other"]

router = APIRouter(prefix="/providers", tags=["providers"], responses=PROTECTED_RESPONSES)


class ProviderOut(ApiModel):
    key: ProviderKey
    label: str
    rule_driven: bool
    checkout_instalments: int
    start_rule: Literal["purchase_date", "months_after_purchase"]
    start_offset_months: int
    monthly_fee_applies: bool


@router.get("", response_model=list[ProviderOut])
def list_providers(_: CurrentUser) -> list[ProviderOut]:
    return [
        ProviderOut(
            key=p.key,  # type: ignore[arg-type]
            label=p.label,
            rule_driven=p.rule_driven,
            checkout_instalments=p.checkout_instalments,
            start_rule=p.start_rule,
            start_offset_months=p.start_offset_months,
            monthly_fee_applies=p.monthly_fee_applies,
        )
        for p in PROVIDERS.values()
    ]
