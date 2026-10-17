"""The Engine 2 feature set (plan P5, task D1; PRD 3.2; ADR D-09).

This is the ONLY place Engine 2 features are computed. Training (`ml/`) imports it; nothing else
re-implements a feature. Every artefact records `FEATURE_SCHEMA_HASH`, and the server refuses to
start if the artefact's hash differs from the one computed here.

Inputs are plain data: no age, employment, persona or repayment history (D-11: repayment history is
a separate rule-based flag, not a model input). Money features are in ringgit; ratios divide by the
expected monthly income and are capped, so a profile with no income gets a large but finite value
instead of infinity.
"""

import hashlib
import json
from dataclasses import dataclass

SEN_PER_RM = 100
RATIO_CAP = 10.0  # a ratio above ten months of income is "far beyond affordable"; cap the rest
DEFINITIONS_VERSION = "v2"  # bump when a feature's definition (not just its name) changes
# v2 (WP16, D-50): the savings buffer feature; Engine 1's running margin starts from the buffer, so
# every margin feature's value can change too.
# Windows and caps that change feature VALUES without changing a name or a direction. They are part
# of the schema hash (the builder in `forecasting/summary.py` imports them), so changing one makes
# an artefact trained under the old values refuse to serve.
RECENT_MONTHS = 3  # complete months averaged for the expected income (every ratio's denominator)
COMMITMENT_MONTHS = 3  # existing BNPL obligations due in this many months are spread over them
COMMITMENT_DAYS_PER_MONTH = 30
FEATURE_CONSTANTS: dict[str, float] = {
    "recent_months": RECENT_MONTHS,
    "commitment_months": COMMITMENT_MONTHS,
    "commitment_days_per_month": COMMITMENT_DAYS_PER_MONTH,
    "ratio_cap": RATIO_CAP,
    "sen_per_rm": SEN_PER_RM,
}

# name -> direction of its effect on risk: +1 raises it, -1 lowers it, 0 none / unknown
MONOTONE_DIRECTIONS: dict[str, int] = {
    "disc_weekly_p50": 1,
    "disc_weekly_p90": 1,
    "disc_volatility": 1,
    "margin_monthly_p50_without": -1,
    "margin_cum_p10_without": -1,
    "income_p10_monthly": -1,
    "instalment_amount": 1,
    "num_instalments": 0,
    "monthly_fee_rate": 1,
    "instalment_to_income": 1,
    "dsr_with_purchase": 1,
    "active_plans_with_purchase": 1,
    "bnpl_outstanding_to_income": 1,
    "upfront_to_income": 1,
    "limit_utilisation_with_purchase": 1,
    "limit_known": 0,
    # D-50: savings the person can fall back on, in months of expected income; added last so the
    # earlier features keep their positions
    "savings_buffer_to_income": -1,
}
FEATURE_NAMES: tuple[str, ...] = tuple(MONOTONE_DIRECTIONS)
# The savings-buffer feature's name, for analysis code that reads stored feature values (D-09:
# names live here only).
BUFFER_FEATURE = "savings_buffer_to_income"
# The features that come from Engine 1's forecast; the ablation retrains without them to show how
# much of the model's skill the forecast contributes.
ENGINE1_FEATURES: tuple[str, ...] = FEATURE_NAMES[:6]


def schema_hash(
    names: list[str], directions: dict[str, int], constants: dict[str, float] | None = None
) -> str:
    blob = json.dumps(
        {
            "names": names,
            "directions": directions,
            "definitions": DEFINITIONS_VERSION,
            "constants": FEATURE_CONSTANTS if constants is None else constants,
        },
        sort_keys=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


FEATURE_SCHEMA_HASH = schema_hash(list(FEATURE_NAMES), MONOTONE_DIRECTIONS)


@dataclass(frozen=True)
class PlanInput:
    instalment_amounts_sen: tuple[int, ...]  # the financed instalments, after the limit cap
    monthly_fee_rate_pct: float
    financed_payable_sen: int  # total the financed part costs to repay, fee included
    upfront_sen: int  # paid at checkout because the provider limit capped financing (D-28)


@dataclass(frozen=True)
class Commitments:
    monthly_bnpl_sen: int  # existing monthly BNPL instalments
    monthly_debt_like_bills_sen: int
    active_plans: int  # existing, before this purchase
    outstanding_bnpl_sen: int  # existing unpaid BNPL, all providers
    provider_outstanding_sen: int  # existing unpaid on this plan's provider
    provider_limit_sen: int | None  # None when the user recorded no limit


@dataclass(frozen=True)
class Engine1Summary:
    disc_weekly_p50_sen: float
    disc_weekly_p90_sen: float
    disc_volatility_sen: float
    margin_monthly_p50_without_sen: float
    margin_cum_p10_without_sen: float
    income_p10_monthly_sen: float


@dataclass(frozen=True)
class FeatureInputs:
    plan: PlanInput
    commitments: Commitments
    engine1: Engine1Summary
    expected_monthly_income_sen: int
    savings_buffer_sen: int = 0  # D-50: what the person recorded; 0 when nothing was


def _rm(sen: float) -> float:
    return sen / SEN_PER_RM


def _ratio(numerator_sen: float, income_sen: int) -> float:
    if numerator_sen <= 0:
        return 0.0
    if income_sen <= 0:
        return RATIO_CAP
    return min(numerator_sen / income_sen, RATIO_CAP)


def compute_features(data: FeatureInputs) -> dict[str, float]:
    plan, owed, e1 = data.plan, data.commitments, data.engine1
    income = data.expected_monthly_income_sen
    count = len(plan.instalment_amounts_sen)
    instalment = sum(plan.instalment_amounts_sen) / count if count else 0.0
    limit = owed.provider_limit_sen
    utilisation = 0.0
    if limit is not None and limit > 0:
        utilisation = min((owed.provider_outstanding_sen + plan.financed_payable_sen) / limit, 1.0)

    values = {
        "disc_weekly_p50": _rm(e1.disc_weekly_p50_sen),
        "disc_weekly_p90": _rm(e1.disc_weekly_p90_sen),
        "disc_volatility": _rm(e1.disc_volatility_sen),
        "margin_monthly_p50_without": _rm(e1.margin_monthly_p50_without_sen),
        "margin_cum_p10_without": _rm(e1.margin_cum_p10_without_sen),
        "income_p10_monthly": _rm(e1.income_p10_monthly_sen),
        "instalment_amount": _rm(instalment),
        "num_instalments": float(count),
        "monthly_fee_rate": float(plan.monthly_fee_rate_pct),
        "instalment_to_income": _ratio(instalment, income),
        "dsr_with_purchase": _ratio(
            owed.monthly_bnpl_sen + instalment + owed.monthly_debt_like_bills_sen, income
        ),
        "active_plans_with_purchase": float(owed.active_plans + 1),
        "bnpl_outstanding_to_income": _ratio(
            owed.outstanding_bnpl_sen + plan.financed_payable_sen, income
        ),
        "upfront_to_income": _ratio(plan.upfront_sen, income),
        "limit_utilisation_with_purchase": utilisation,
        "limit_known": 1.0 if limit is not None else 0.0,
        "savings_buffer_to_income": _ratio(data.savings_buffer_sen, income),
    }
    return {name: values[name] for name in FEATURE_NAMES}


def as_vector(computed: dict[str, float]) -> list[float]:
    """Feature values in the declared order, for a model."""
    return [computed[name] for name in FEATURE_NAMES]
