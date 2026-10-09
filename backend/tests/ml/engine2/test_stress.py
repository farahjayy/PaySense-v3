from datetime import date

import numpy as np
import pytest

from app.engines.forecasting.models import MovingAverage
from app.engines.risk.features import FEATURE_SCHEMA_HASH
from ml.datagen.params import load_params
from ml.datagen.profile import generate_dated_profile, generate_profile
from ml.engine2_train.labels import label_profile, prepare
from ml.engine2_train.stress import (
    VARIANTS,
    Variant,
    check_provenance,
    evaluate_variant,
    income_down,
    missing_month,
    ptptn_delayed,
    run_variant,
    stale,
)

AS_OF = date(2025, 12, 28)
PARAMS = load_params()
MODEL = MovingAverage(13)
SEED = 5


def row(day, amount, kind="expense", category="Food", description="x"):
    return {"date": day, "amount_sen": amount, "type": kind, "category": category,
            "description": description}  # fmt: skip


def item(kind="income", cadence="semester", anchor=date(2025, 9, 10), name="ptptn"):
    return {"kind": kind, "name": name, "match_text": name, "amount_sen": 250000,
            "cadence": cadence, "custom_interval_days": None, "anchor_date": anchor,
            "active": True}  # fmt: skip


def test_income_down_cuts_real_income_only():
    rows = [
        row(date(2025, 12, 1), 100000, "income", "Allowance"),
        row(date(2025, 12, 2), 50000, "income", "Refund"),
        row(date(2025, 12, 3), 9000),
    ]

    out = income_down(rows, AS_OF)

    assert [r["amount_sen"] for r in out] == [80000, 50000, 9000]
    assert rows[0]["amount_sen"] == 100000  # the input is untouched


def test_stale_drops_the_last_three_weeks():
    rows = [row(date(2025, 12, 5), 1), row(date(2025, 12, 8), 2), row(date(2025, 12, 27), 3)]

    assert [r["amount_sen"] for r in stale(rows, AS_OF)] == [1]


def test_missing_month_removes_the_whole_previous_month_only():
    rows = [row(date(2025, 10, 30), 1), row(date(2025, 11, 1), 2), row(date(2025, 11, 30), 3),
            row(date(2025, 12, 1), 4)]  # fmt: skip

    assert [r["amount_sen"] for r in missing_month(rows, AS_OF)] == [1, 4]


def test_the_variants_are_identity_and_the_four_pre_registered_ones():
    assert set(VARIANTS) == {
        "identity", "income_down_20", "stale_3_weeks", "missing_month", "ptptn_delayed"
    }  # fmt: skip
    assert VARIANTS["identity"] == Variant()


# ---------------------------------------------------------------- the PTPTN scenario (audit H4)
def test_the_next_semester_income_is_pushed_one_semester_on_and_later_ones_stay():
    out = ptptn_delayed([item(anchor=date(2025, 9, 10))], AS_OF)

    # the next disbursement after 28 Dec 2025 is 10 Mar 2026; the anchor now sits at 10 Sep 2026
    assert out[0]["anchor_date"] == date(2026, 9, 10)


def test_only_semester_income_is_touched():
    items = [
        item("income", "monthly", date(2025, 12, 1), "allowance"),
        item("bill", "semester", date(2025, 9, 1), "insurance"),
        item("bill", "monthly", date(2025, 12, 5), "rent"),
    ]

    assert ptptn_delayed(items, AS_OF) == items


def test_the_input_items_are_not_modified():
    items = [item()]

    ptptn_delayed(items, AS_OF)

    assert items[0]["anchor_date"] == date(2025, 9, 10)


def holder_and_non_holder(count=80):
    holder = other = None
    for index in range(count):
        profile = generate_dated_profile(PARAMS, SEED, index)
        has_semester = any(i["cadence"] == "semester" for i in prepare(profile)["items"])
        if has_semester and holder is None:
            holder = index
        if not has_semester and other is None:
            other = index
        if holder is not None and other is not None:
            return holder, other
    raise AssertionError("the sample had no PTPTN holder or no non-holder")


def test_for_a_ptptn_holder_the_variant_changes_what_the_pipeline_sees_and_for_others_nothing():
    holder, other = holder_and_non_holder()
    delayed = VARIANTS["ptptn_delayed"]

    changed = run_variant(PARAMS, SEED, [holder], delayed, MODEL, paths=150)
    same = run_variant(PARAMS, SEED, [holder], VARIANTS["identity"], MODEL, paths=150)
    untouched = run_variant(PARAMS, SEED, [other], delayed, MODEL, paths=150)
    baseline = run_variant(PARAMS, SEED, [other], VARIANTS["identity"], MODEL, paths=150)

    assert changed.changed == (True,)
    assert not np.array_equal(changed.vectors, same.vectors) or changed.labels != same.labels
    assert untouched.changed == (False,)
    assert np.array_equal(untouched.vectors, baseline.vectors)
    assert np.array_equal(untouched.labels, baseline.labels)


# ---------------------------------------------------------------- the pipeline under a variant
def test_a_transform_changes_what_the_pipeline_sees_without_touching_the_profile():
    profile = generate_profile(PARAMS, 5, 1, persona="budget_conscious")
    before = prepare(profile)
    after = prepare(profile, stale)

    assert len(after["rows"]) < len(before["rows"])
    assert len(profile.transactions) == len(before["rows"])


def test_the_identity_variant_reproduces_the_stored_label_exactly():
    for index in range(3):
        profile = generate_dated_profile(PARAMS, SEED, index)
        stored = label_profile(profile, MODEL, SEED, paths=120)
        again = run_variant(PARAMS, SEED, [index], Variant(), MODEL, paths=120)
        if stored is None:
            assert again.locked == 1
        else:
            assert again.labels[0] == stored["label"]  # same paths, same seed: same number


def test_a_variant_run_scores_the_model_against_the_new_simulated_label():
    predict = lambda x: np.full(len(x), 0.5)  # noqa: E731 - a constant model is enough here

    out = evaluate_variant(PARAMS, 5, [0, 1, 2], VARIANTS["income_down_20"], predict, MODEL, 100)

    assert out["profiles"] + out["locked"] == 3
    if out["profiles"]:
        assert 0 <= out["brier"] <= 1 and out["mean_prediction"] == 0.5
        assert 0 <= out["band_agreement"] <= 1 and out["changed_inputs"] >= 0


# ---------------------------------------------------------------- provenance checks
def manifest(**overrides):
    base = {"params_hash": PARAMS.hash(), "feature_schema_hash": FEATURE_SCHEMA_HASH,
            "file": {"sha256": "abc"}}  # fmt: skip
    return base | overrides


def test_a_matching_manifest_passes():
    check_provenance(manifest(), {"labels_sha256": "abc"}, PARAMS)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"params_hash": "0" * 16}, "different generator parameters"),
        ({"feature_schema_hash": "0" * 16}, "different feature schema"),
        ({"file": {"sha256": "other"}}, "different labels"),
    ],
)
def test_stress_testing_refuses_labels_or_code_the_model_was_not_made_with(override, message):
    with pytest.raises(ValueError, match=message):
        check_provenance(manifest(**override), {"labels_sha256": "abc"}, PARAMS)
