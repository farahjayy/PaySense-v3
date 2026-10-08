"""Existing BNPL plans and their payment events (plan P2, A7).

Every plan is built with the app's own `propose_plan`, so the generator applies exactly the same
schedule rules, fee handling and provider-limit split (D-28) as the product. Payment behaviour
(on time / late but paid / missed) follows the cited CCOB shares; it feeds only the repayment
history *flag* demonstrations, never a model label (D-11).
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from app.db.plans import instalment_description
from app.domain.categorize import BNPL
from app.domain.plan_builder import PlanProposal, ProposalError, propose_plan
from app.domain.schedule import add_months
from ml.datagen.params import Params
from ml.datagen.types import Txn

NAMED_PROVIDERS = ("spaylater", "tiktok_paylater", "atome")
PROVIDERS = (*NAMED_PROVIDERS, "other")
ITEM_NAMES = (
    "Phone case",
    "Earbuds",
    "Sneakers",
    "Textbook bundle",
    "Skincare set",
    "Laptop stand",
    "Backpack",
    "Power bank",
    "Keyboard",
    "Jacket",
)
OTHER_PROVIDER_LABELS = ("Grab PayLater", "Boost PayFlex", "Kredivo", "Pace")
LOOKBACK_DAYS = 60  # plans can start before the visible history
MAX_FIRST_PAYMENT_SLACK_DAYS = 3  # a typed first date is rarely exactly one month out


@dataclass(frozen=True)
class GeneratedPlan:
    key: str
    item_name: str
    proposal: PlanProposal
    paid_dates: dict[int, date]  # seq -> the day it was paid (only if paid on or before today)


@dataclass
class BnplResult:
    plans: list[GeneratedPlan] = field(default_factory=list)
    payments: list[Txn] = field(default_factory=list)
    limits: dict[str, int | None] = field(default_factory=dict)  # recorded limit, None = unknown


def _lognormal(rng: np.random.Generator, median: float, sigma: float) -> float:
    return float(median * np.exp(rng.normal(0.0, sigma)))


def _choose(rng: np.random.Generator, names: tuple[str, ...], weights: list[float]) -> str:
    probabilities = np.array(weights) / sum(weights)
    return str(rng.choice(names, p=probabilities))


def _true_limits(
    params: Params, rng: np.random.Generator
) -> tuple[dict[str, int], dict[str, int | None]]:
    """What each provider really allows, and what the user has recorded in the app."""
    actual: dict[str, int] = {}
    recorded: dict[str, int | None] = {}
    for provider in NAMED_PROVIDERS:
        limit = int(
            min(
                _lognormal(
                    rng, params[f"bnpl.limit_median_sen.{provider}"], params["bnpl.limit_sigma"]
                ),
                params[f"bnpl.limit_cap_sen.{provider}"],
            )
        )
        actual[provider] = max(limit, 1000)
        known = rng.random() < params["bnpl.limit_known_probability"]
        recorded[provider] = actual[provider] if known else None
    return actual, recorded


def _outcome_shares(params: Params) -> np.ndarray:
    shares = np.array(
        [
            params["repayment.on_time_share"],
            params["repayment.late_but_paid_share"],
            params["repayment.missed_share"],
        ]
    )
    return shares / shares.sum()  # the cited shares plus the assumed miss rate, renormalised


def _unpaid_total_on(plans: list[GeneratedPlan], provider: str, day: date) -> int:
    """What earlier plans on this provider still owed on `day` (the limit they are using)."""
    owed = 0
    for plan in plans:
        if plan.proposal.provider != provider:
            continue
        for seq, instalment in enumerate(plan.proposal.instalments, start=1):
            paid_on = plan.paid_dates.get(seq)
            if paid_on is None or paid_on > day:
                owed += instalment.amount_sen
    return owed


def _propose(
    params: Params,
    provider: str,
    purchase: date,
    count: int,
    price: int,
    remaining: int | None,
    rng: np.random.Generator,
) -> PlanProposal:
    fee = (
        0
        if count in params[f"bnpl.zero_fee_instalments.{provider}"]
        else params["bnpl.long_plan_fee_rate_pct"]
    )
    if provider == "other":
        total = int(round(price * (1 + fee * count / 100)))
        first = add_months(purchase, 1) + timedelta(
            days=int(rng.integers(0, MAX_FIRST_PAYMENT_SLACK_DAYS + 1))
        )
        return propose_plan(
            provider="other",
            purchase_date=purchase,
            num_instalments=count,
            first_payment_date=first,
            provider_label=OTHER_PROVIDER_LABELS[int(rng.integers(len(OTHER_PROVIDER_LABELS)))],
            total_payable_sen=total,
        )
    return propose_plan(
        provider=provider,
        purchase_date=purchase,
        num_instalments=count,
        total_price_sen=price,
        monthly_fee_rate_pct=fee,
        remaining_limit_sen=remaining,
    )


def _settle(
    params: Params, proposal: PlanProposal, end: date, shares: np.ndarray, rng: np.random.Generator
) -> dict[int, date]:
    """When each instalment was actually paid (absent = not paid by `end`)."""
    low, high = params["repayment.late_days_range"]
    paid: dict[int, date] = {}
    for seq, instalment in enumerate(proposal.instalments, start=1):
        if instalment.paid_at_checkout:
            paid[seq] = proposal.purchase_date
            continue
        if instalment.due_date > end:
            continue
        outcome = int(rng.choice(3, p=shares))
        if outcome == 0:
            when = instalment.due_date
        elif outcome == 1:
            when = instalment.due_date + timedelta(days=int(rng.integers(low, high + 1)))
        else:
            continue  # missed: still unpaid
        if when <= end:
            paid[seq] = when
    return paid


def _payment_events(
    key: str, item_name: str, plan: GeneratedPlan, start: date, end: date
) -> list[Txn]:
    proposal = plan.proposal
    meta = {
        "provider_label": proposal.provider_label,
        "num_installments": proposal.num_installments,
        "item_name": item_name,
    }
    events: list[Txn] = []
    if proposal.upfront_sen > 0 and start <= proposal.purchase_date <= end:
        description = f"{proposal.provider_label} checkout payment — {item_name}"
        events.append(
            Txn(proposal.purchase_date, proposal.upfront_sen, "expense", BNPL, description, key)
        )
    for seq, paid_on in plan.paid_dates.items():
        if start <= paid_on <= end:
            amount = proposal.instalments[seq - 1].amount_sen
            events.append(
                Txn(paid_on, amount, "expense", BNPL, instalment_description(meta, seq), key)
            )
    return events


def generate_bnpl(
    params: Params, persona: str, start: date, end: date, rng: np.random.Generator
) -> BnplResult:
    result = BnplResult()
    if rng.random() >= params[f"bnpl.ownership_probability.{persona}"]:
        return result
    actual, result.limits = _true_limits(params, rng)
    count = 1 + int(rng.poisson(params[f"bnpl.active_plans_extra_mean.{persona}"]))
    span = (end - start).days + LOOKBACK_DAYS
    purchases = sorted(
        start - timedelta(days=LOOKBACK_DAYS) + timedelta(days=int(rng.integers(0, span + 1)))
        for _ in range(count)
    )
    weights = [params[f"bnpl.provider_weights.{p}"] for p in PROVIDERS]
    shares = _outcome_shares(params)
    low, high = params["bnpl.price_range_sen"]

    for index, purchase in enumerate(purchases):
        provider = _choose(rng, PROVIDERS, weights)
        options = params[f"bnpl.instalment_options.{provider}"]
        instalments = int(rng.choice(options))
        price = int(
            np.clip(
                _lognormal(rng, params["bnpl.price_median_sen"], params["bnpl.price_sigma"]),
                low,
                high,
            )
        )
        remaining = None
        if provider in NAMED_PROVIDERS:
            remaining = max(
                actual[provider] - _unpaid_total_on(result.plans, provider, purchase), 0
            )
        try:
            proposal = _propose(params, provider, purchase, instalments, price, remaining, rng)
        except ProposalError:
            continue  # no limit left for this one: the student simply did not buy it
        key = f"plan-{index}"
        item = ITEM_NAMES[int(rng.integers(len(ITEM_NAMES)))]
        plan = GeneratedPlan(key, item, proposal, _settle(params, proposal, end, shares, rng))
        result.plans.append(plan)
        result.payments += _payment_events(key, item, plan, start, end)

    result.payments.sort(key=lambda t: (t.date, t.description))
    return result
