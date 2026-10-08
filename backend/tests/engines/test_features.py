import dataclasses
import re
from pathlib import Path

import pytest

from app.engines.risk import features
from app.engines.risk.features import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_HASH,
    MONOTONE_DIRECTIONS,
    Commitments,
    Engine1Summary,
    FeatureInputs,
    PlanInput,
    compute_features,
    schema_hash,
)


def inputs(**overrides):
    base = FeatureInputs(
        plan=PlanInput(
            instalment_amounts_sen=(20000, 20000, 20000),
            monthly_fee_rate_pct=0.0,
            financed_payable_sen=60000,
            upfront_sen=0,
        ),
        commitments=Commitments(
            monthly_bnpl_sen=10000,
            monthly_debt_like_bills_sen=30000,
            active_plans=1,
            outstanding_bnpl_sen=50000,
            provider_outstanding_sen=30000,
            provider_limit_sen=200000,
        ),
        engine1=Engine1Summary(
            disc_weekly_p50_sen=7000,
            disc_weekly_p90_sen=12000,
            disc_volatility_sen=3000,
            margin_monthly_p50_without_sen=40000,
            margin_cum_p10_without_sen=-5000,
            income_p10_monthly_sen=150000,
        ),
        expected_monthly_income_sen=200000,
    )
    return dataclasses.replace(base, **overrides)


def test_there_are_sixteen_features_in_a_fixed_order():
    assert len(FEATURE_NAMES) == 16 and len(set(FEATURE_NAMES)) == 16
    assert FEATURE_NAMES[0] == "disc_weekly_p50" and FEATURE_NAMES[-1] == "limit_known"


def test_every_feature_has_a_monotone_direction_of_minus_one_zero_or_one():
    assert set(MONOTONE_DIRECTIONS) == set(FEATURE_NAMES)
    assert set(MONOTONE_DIRECTIONS.values()) <= {-1, 0, 1}
    assert MONOTONE_DIRECTIONS["margin_monthly_p50_without"] == -1
    assert MONOTONE_DIRECTIONS["instalment_to_income"] == 1
    assert MONOTONE_DIRECTIONS["num_instalments"] == 0 and MONOTONE_DIRECTIONS["limit_known"] == 0


def test_the_engine_one_features_are_in_ringgit():
    f = compute_features(inputs())

    assert f["disc_weekly_p50"] == 70.0 and f["disc_weekly_p90"] == 120.0
    assert f["disc_volatility"] == 30.0
    assert f["margin_monthly_p50_without"] == 400.0
    assert f["margin_cum_p10_without"] == -50.0
    assert f["income_p10_monthly"] == 1500.0


def test_the_plan_features_are_the_financed_instalment_after_the_limit_cap():
    f = compute_features(inputs())

    assert f["instalment_amount"] == 200.0  # mean financed instalment in ringgit
    assert f["num_instalments"] == 3 and f["monthly_fee_rate"] == 0.0
    assert f["instalment_to_income"] == pytest.approx(0.10)  # 200 / 2000


def test_dsr_adds_existing_bnpl_the_new_instalment_and_debt_like_bills():
    f = compute_features(inputs())

    # (RM100 existing BNPL + RM200 new + RM300 bills) / RM2,000
    assert f["dsr_with_purchase"] == pytest.approx(0.30)


def test_outstanding_bnpl_includes_the_new_financed_amount():
    f = compute_features(inputs())

    assert f["active_plans_with_purchase"] == 2
    assert f["bnpl_outstanding_to_income"] == pytest.approx((500 + 600) / 2000)


def test_a_purchase_that_fits_the_limit_pays_nothing_upfront():
    f = compute_features(inputs())

    assert f["upfront_to_income"] == 0.0
    assert f["limit_known"] == 1
    assert f["limit_utilisation_with_purchase"] == pytest.approx((300 + 600) / 2000)


def test_a_limit_capped_purchase_shows_its_checkout_payment_and_a_full_limit():
    capped = inputs(
        plan=PlanInput(
            instalment_amounts_sen=(10000, 10000),
            monthly_fee_rate_pct=1.5,
            financed_payable_sen=20000,
            upfront_sen=40000,
        ),
        commitments=Commitments(0, 0, 0, 0, 0, provider_limit_sen=20000),
    )

    f = compute_features(capped)

    assert f["upfront_to_income"] == pytest.approx(400 / 2000)
    assert f["limit_utilisation_with_purchase"] == pytest.approx(1.0)
    assert f["instalment_amount"] == 100.0 and f["monthly_fee_rate"] == 1.5


def test_without_a_recorded_limit_utilisation_is_zero_and_the_flag_says_so():
    no_limit = inputs(
        commitments=Commitments(10000, 30000, 1, 50000, 30000, provider_limit_sen=None)
    )

    f = compute_features(no_limit)

    assert f["limit_utilisation_with_purchase"] == 0.0 and f["limit_known"] == 0


def test_no_income_gives_a_large_but_finite_ratio_not_infinity():
    broke = inputs(expected_monthly_income_sen=0)

    f = compute_features(broke)

    assert all(value == value and abs(value) < 1e9 for value in f.values())
    assert f["instalment_to_income"] == features.RATIO_CAP


def test_ratios_are_capped_so_one_extreme_profile_cannot_dominate_training():
    f = compute_features(inputs(expected_monthly_income_sen=1))

    assert f["dsr_with_purchase"] == features.RATIO_CAP
    assert f["bnpl_outstanding_to_income"] == features.RATIO_CAP


def test_features_come_back_in_the_declared_order_as_a_vector():
    vector = features.as_vector(compute_features(inputs()))

    assert len(vector) == 16 and vector[FEATURE_NAMES.index("num_instalments")] == 3


def test_the_schema_hash_changes_with_names_order_or_directions():
    names = list(FEATURE_NAMES)
    base = schema_hash(names, MONOTONE_DIRECTIONS)

    assert base == FEATURE_SCHEMA_HASH
    assert schema_hash(names[::-1], MONOTONE_DIRECTIONS) != base
    assert schema_hash([*names[:-1], "other"], MONOTONE_DIRECTIONS) != base
    assert schema_hash(names, {**MONOTONE_DIRECTIONS, "limit_known": 1}) != base


FORBIDDEN = ("age", "employ", "persona", "repayment", "overdue", "late_pay", "gender", "race")


def test_no_forbidden_attribute_is_a_feature_or_an_input():
    for name in FEATURE_NAMES:
        assert not any(bad in name for bad in FORBIDDEN), name
    declared = {
        f.name
        for cls in (FeatureInputs, PlanInput, Commitments, Engine1Summary)
        for f in dataclasses.fields(cls)
    }
    assert not any(bad in field for field in declared for bad in FORBIDDEN)


def test_features_are_computed_in_exactly_one_module():
    """Engine 2 features live in features.py (D-09): no other module names them in code."""
    root = Path(features.__file__).resolve().parents[3]
    # four features share their name with a plan field that the rest of the app uses legitimately
    shared = {"num_instalments", "monthly_fee_rate", "instalment_amount", "limit_known"}
    derived = [name for name in FEATURE_NAMES if name not in shared]
    pattern = re.compile(r"\b(" + "|".join(derived) + r")\b")
    offenders = []
    for folder in ("app", "ml"):
        for path in (root / folder).rglob("*.py"):
            if path == Path(features.__file__).resolve():
                continue
            if pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_the_engine_one_features_are_the_six_forecast_derived_ones():
    assert FEATURE_NAMES[:6] == features.ENGINE1_FEATURES
    assert set(features.ENGINE1_FEATURES) <= set(FEATURE_NAMES)
    assert "instalment_amount" not in features.ENGINE1_FEATURES
