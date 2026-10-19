"""BNPL provider rules as data (ADR D-24). Served by the API; never mirrored in the frontend (D-17).

Only SPayLater, TikTok PayLater and Atome are rule-driven — their rules are confirmed from real
students' checkouts (the team's billing-rules research note). Every other provider is the manual
"Other provider" path: the user types the dates and amounts from their own checkout and the app
applies no rule and no fee formula. A provider becomes rule-driven only after a real checkout
example is recorded in that file and a test pins its schedule.

Fields
  checkout_instalments   leading instalments charged at checkout, on the purchase date
                         (Atome: 1 of the plan's payments).
  start_rule             how the first due date follows from the purchase date:
                           "purchase_date"          the purchase date itself
                           "months_after_purchase"  purchase date + start_offset_months
                         Later instalments repeat that day-of-month each month.
  monthly_fee_applies    False forces the fee to 0 whatever the caller passes.
  rule_driven            False for the manual path: no start rule, no fee, no limit cap.
"""

from dataclasses import dataclass
from typing import Literal

StartRule = Literal["purchase_date", "months_after_purchase"]


@dataclass(frozen=True)
class ProviderConfig:
    key: str
    label: str
    rule_driven: bool
    checkout_instalments: int = 0
    start_rule: StartRule = "purchase_date"
    start_offset_months: int = 0
    monthly_fee_applies: bool = True


PROVIDERS: dict[str, ProviderConfig] = {
    "spaylater": ProviderConfig(
        key="spaylater",
        label="SPayLater",
        rule_driven=True,
        start_rule="months_after_purchase",
        start_offset_months=1,
    ),
    "tiktok_paylater": ProviderConfig(
        key="tiktok_paylater",
        label="TikTok PayLater",
        rule_driven=True,
        start_rule="months_after_purchase",
        start_offset_months=1,
    ),
    "atome": ProviderConfig(key="atome", label="Atome", rule_driven=True, checkout_instalments=1),
    "other": ProviderConfig(
        key="other", label="Other provider", rule_driven=False, monthly_fee_applies=False
    ),
}

PROVIDER_KEYS: tuple[str, ...] = tuple(PROVIDERS)
FALLBACK_PROVIDER = "other"


def get_provider(key: str) -> ProviderConfig:
    """Config for `key`; anything unknown behaves as the manual "other" provider."""
    return PROVIDERS.get(key, PROVIDERS[FALLBACK_PROVIDER])
