"""Turn what a user entered (plus their remaining provider limit) into a plan proposal.

One pure function serves both the preview and the create endpoints, so the schedule a person sees
before confirming is by construction the schedule that gets saved. Rule-driven providers go
through the provider rules and the limit split (ADR D-24, D-28); the manual "Other provider" path
uses exactly the dates and amounts typed, with no rule, no fee and no limit.
"""

from dataclasses import dataclass
from datetime import date

from app.domain.providers import ProviderConfig, get_provider
from app.domain.schedule import (
    MAX_INSTALMENTS,
    MIN_INSTALMENTS,
    Instalment,
    build_manual_schedule,
    build_schedule,
    split_for_limit,
)


class ProposalError(ValueError):
    """The input cannot become a plan. `code` is stable and user-facing messages are in English."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PlanProposal:
    provider: str
    provider_label: str
    schedule_source: str  # "provider_rule" | "manual"
    total_price_sen: int  # the full purchase price
    financed_sen: int  # the part put on the provider
    upfront_sen: int  # the part paid at checkout because the limit cannot cover it
    monthly_fee_rate_pct: float
    num_installments: int
    purchase_date: date
    first_payment_date: date
    instalments: tuple[Instalment, ...]
    limit_applied: bool
    remaining_limit_sen: int | None

    @property
    def total_payable_sen(self) -> int:
        """What the financed part costs to repay, fee included: the sum of the real instalments."""
        return sum(i.amount_sen for i in self.instalments)

    @property
    def cash_at_purchase_sen(self) -> int:
        """Cash leaving the user on the purchase date: the excess plus any instalment due at
        checkout (an Atome first payment)."""
        return self.upfront_sen + sum(i.amount_sen for i in self.instalments if i.paid_at_checkout)


def _check_count(count: int) -> None:
    if not MIN_INSTALMENTS <= count <= MAX_INSTALMENTS:
        raise ProposalError(
            "invalid_instalments",
            f"Instalments must be between {MIN_INSTALMENTS} and {MAX_INSTALMENTS}.",
        )


def _manual(
    config: ProviderConfig,
    *,
    purchase_date: date,
    num_instalments: int,
    first_payment_date: date | None,
    provider_label: str | None,
    instalment_sen: int | None,
    total_payable_sen: int | None,
    total_price_sen: int | None,
) -> PlanProposal:
    if total_price_sen is not None:
        raise ProposalError(
            "price_not_allowed",
            "For another provider, enter the instalment amount or total payable at checkout.",
        )
    if first_payment_date is None:
        raise ProposalError("first_payment_date_required", "Enter the first payment date.")
    label = (provider_label or "").strip()
    if not label:
        raise ProposalError("provider_label_required", "Enter the provider's name.")
    if (instalment_sen is None) == (total_payable_sen is None):
        raise ProposalError(
            "amount_required", "Enter either the instalment amount or the total payable, not both."
        )
    try:
        instalments = build_manual_schedule(
            first_payment_date,
            num_instalments,
            instalment_sen=instalment_sen,
            total_payable_sen=total_payable_sen,
        )
    except ValueError as err:
        raise ProposalError("amount_too_small", str(err)) from err
    total = sum(i.amount_sen for i in instalments)
    return PlanProposal(
        provider=config.key,
        provider_label=label,
        schedule_source="manual",
        total_price_sen=total,
        financed_sen=total,
        upfront_sen=0,
        monthly_fee_rate_pct=0,
        num_installments=num_instalments,
        purchase_date=purchase_date,
        first_payment_date=instalments[0].due_date,
        instalments=tuple(instalments),
        limit_applied=False,
        remaining_limit_sen=None,
    )


def _rule_driven(
    config: ProviderConfig,
    *,
    purchase_date: date,
    num_instalments: int,
    first_payment_date: date | None,
    total_price_sen: int | None,
    monthly_fee_rate_pct: float,
    remaining_limit_sen: int | None,
) -> PlanProposal:
    if total_price_sen is None:
        raise ProposalError("price_required", "Enter the price.")
    rate = monthly_fee_rate_pct if config.monthly_fee_applies else 0
    split = split_for_limit(total_price_sen, remaining_limit_sen, rate, num_instalments)
    if split.financed_sen == 0:
        raise ProposalError(
            "limit_exhausted",
            f"There is no {config.label} limit left for this purchase. Pay it up front or "
            "raise the limit you recorded.",
        )
    try:
        instalments = build_schedule(
            config.key,
            split.financed_sen,
            rate,
            num_instalments,
            purchase_date,
            first_payment_date,
        )
    except ValueError as err:
        raise ProposalError("amount_too_small", str(err)) from err
    return PlanProposal(
        provider=config.key,
        provider_label=config.label,
        schedule_source="provider_rule",
        total_price_sen=total_price_sen,
        financed_sen=split.financed_sen,
        upfront_sen=split.upfront_sen,
        monthly_fee_rate_pct=rate,
        num_installments=num_instalments,
        purchase_date=purchase_date,
        first_payment_date=instalments[0].due_date,
        instalments=tuple(instalments),
        limit_applied=split.limit_applied,
        remaining_limit_sen=remaining_limit_sen,
    )


def propose_plan(
    *,
    provider: str,
    purchase_date: date,
    num_instalments: int,
    total_price_sen: int | None = None,
    monthly_fee_rate_pct: float = 0,
    first_payment_date: date | None = None,
    provider_label: str | None = None,
    instalment_sen: int | None = None,
    total_payable_sen: int | None = None,
    remaining_limit_sen: int | None = None,
) -> PlanProposal:
    config = get_provider(provider)
    if config.key != provider:
        raise ProposalError("unknown_provider", f"Unknown provider: {provider!r}.")
    _check_count(num_instalments)
    if config.rule_driven:
        if any(v is not None for v in (provider_label, instalment_sen, total_payable_sen)):
            raise ProposalError(
                "manual_fields_not_allowed",
                f"{config.label} follows its own rules; enter the price instead.",
            )
        return _rule_driven(
            config,
            purchase_date=purchase_date,
            num_instalments=num_instalments,
            first_payment_date=first_payment_date,
            total_price_sen=total_price_sen,
            monthly_fee_rate_pct=monthly_fee_rate_pct,
            remaining_limit_sen=remaining_limit_sen,
        )
    return _manual(
        config,
        purchase_date=purchase_date,
        num_instalments=num_instalments,
        first_payment_date=first_payment_date,
        provider_label=provider_label,
        instalment_sen=instalment_sen,
        total_payable_sen=total_payable_sen,
        total_price_sen=total_price_sen,
    )
