"""The proposed purchase Engine 2 will be asked about (plan P2, A8).

The price is a multiple of the student's expected monthly income, drawn log-uniformly over a wide
range so the training set contains clearly safe, borderline and clearly unaffordable cases
(coverage, not realism: `purchase.price_to_monthly_income_range` is an assumption). The plan is
built with the app's own `propose_plan` against the provider limit left at `as_of`, so limit-capped
purchases (D-28) occur naturally.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np

from app.domain.plan_builder import PlanProposal, ProposalError
from ml.datagen.bnpl import (
    NAMED_PROVIDERS,
    PROVIDERS,
    BnplResult,
    build_proposal,
    unpaid_total_on,
)
from ml.datagen.params import Params

MAX_ATTEMPTS = 6  # redraw if the chosen provider has no limit left, then fall back to "other"


@dataclass(frozen=True)
class PurchaseProposal:
    price_sen: int
    proposal: PlanProposal


def sample_purchase(
    params: Params,
    expected_monthly_income_sen: int,
    as_of: date,
    bnpl: BnplResult,
    rng: np.random.Generator,
) -> PurchaseProposal:
    income = max(expected_monthly_income_sen, params["purchase.income_floor_sen"])
    low, high = params["purchase.price_to_monthly_income_range"]
    ratio = float(np.exp(rng.uniform(np.log(low), np.log(high))))
    price = int(
        np.clip(
            income * ratio, params["purchase.price_floor_sen"], params["purchase.price_cap_sen"]
        )
    )
    weights = np.array([params[f"bnpl.provider_weights.{p}"] for p in PROVIDERS])
    weights = weights / weights.sum()

    for attempt in range(MAX_ATTEMPTS):
        provider = "other" if attempt == MAX_ATTEMPTS - 1 else str(rng.choice(PROVIDERS, p=weights))
        count = int(rng.choice(params[f"bnpl.instalment_options.{provider}"]))
        remaining = None
        recorded = bnpl.limits.get(provider) if provider in NAMED_PROVIDERS else None
        if recorded is not None:  # the app only caps on a limit the user has recorded (D-28)
            remaining = max(recorded - unpaid_total_on(bnpl.plans, provider, as_of), 0)
        try:
            proposal = build_proposal(params, provider, as_of, count, price, remaining, rng)
        except ProposalError:
            continue
        return PurchaseProposal(price, proposal)
    raise RuntimeError("could not build any purchase proposal")  # unreachable: 'other' has no limit
