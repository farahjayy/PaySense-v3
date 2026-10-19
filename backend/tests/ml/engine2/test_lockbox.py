import json

import numpy as np
import pytest

from app.engines.risk.features import FEATURE_NAMES, MONOTONE_DIRECTIONS
from ml.engine2_train.data import LOW_BASELINE, Dataset
from ml.engine2_train.lockbox import append_log, brier_breakdown, score_lockbox
from ml.engine2_train.metrics import band_agreement, brier
from ml.engine2_train.models import fit_soft, logistic_sign_check


def box(y, p_without):
    y, p_without = np.array(y, dtype=float), np.array(p_without, dtype=float)
    return Dataset(np.zeros((len(y), len(FEATURE_NAMES))), y, np.arange(len(y)), FEATURE_NAMES,
                   p_without=p_without)  # fmt: skip


Y = [0.0, 0.0, 0.0, 0.02, 0.5, 0.8, 1.0, 1.0]
BASE = [0.0, 0.0, 0.05, 0.05, 0.4, 0.6, 1.0, 1.0]
PRED = np.array([0.1, 0.0, 0.2, 0.0, 0.4, 0.9, 0.9, 1.0])


# ---------------------------------------------------------------- M1: the subgroup's own constant
def test_each_subgroup_is_benchmarked_against_the_constant_of_its_own_development_mean():
    lockbox = box(Y, BASE)

    out = score_lockbox(lockbox, PRED, PRED, PRED, base=0.437, group_bases={LOW_BASELINE: 0.07})

    group = out["subgroups"][LOW_BASELINE]
    mask = lockbox.subgroups()[LOW_BASELINE]
    assert group["brier_constant"] == pytest.approx(brier(np.full(4, 0.07), lockbox.y[mask]))
    assert group["constant_value"] == 0.07
    assert out["constant_brier"] == pytest.approx(brier(np.full(8, 0.437), lockbox.y))


# ---------------------------------------------------------------- M3a: the subgroup in full
def test_the_subgroup_gets_band_agreement_reliability_and_both_kinds_of_prediction():
    lockbox = box(Y, BASE)
    raw = np.clip(PRED + 0.05, 0, 1)

    out = score_lockbox(lockbox, raw, PRED, PRED, base=0.4, group_bases={LOW_BASELINE: 0.07})

    group = out["subgroups"][LOW_BASELINE]
    mask = lockbox.subgroups()[LOW_BASELINE]
    agreement, confusion = band_agreement(PRED[mask], lockbox.y[mask])
    assert group["band_agreement"] == pytest.approx(agreement)
    assert np.array(group["band_confusion_label_rows_model_columns"]).sum() == int(mask.sum())
    assert sum(b["profiles"] for b in group["reliability"]) == int(mask.sum())
    assert group["brier_raw"] == pytest.approx(brier(raw[mask], lockbox.y[mask]))
    assert {"brier", "ece", "calibration_slope"} <= set(group["calibrated"])
    assert {"brier", "ece", "calibration_slope"} <= set(group["raw"])
    json.dumps(out, allow_nan=False)  # a one-class subgroup gives null, never NaN, in the record


# ---------------------------------------------------------------- M3b: the label classes
def test_the_brier_breakdown_splits_the_lockbox_by_label_class_and_by_baseline():
    lockbox = box(Y, BASE)

    out = brier_breakdown(lockbox, PRED, PRED, PRED, base=0.4)

    assert out["label_exactly_0"]["profiles"] == 3
    assert out["label_between_0_and_1"]["profiles"] == 3
    assert out["label_exactly_1"]["profiles"] == 2
    zero = lockbox.y == 0
    assert out["label_exactly_0"]["brier_calibrated"] == pytest.approx(
        brier(PRED[zero], lockbox.y[zero])
    )
    assert out["p_without_between_0_and_1"]["profiles"] == 4
    assert out["p_without_exactly_0_or_1"]["profiles"] == 4
    shares = [out[k]["share_of_squared_error"] for k in
              ("label_exactly_0", "label_between_0_and_1", "label_exactly_1")]  # fmt: skip
    assert sum(shares) == pytest.approx(1.0)
    assert out["label_exactly_0"]["brier_constant"] == pytest.approx(
        brier(np.full(3, 0.4), lockbox.y[zero])
    )


def test_the_breakdown_leaves_out_a_class_that_is_empty_and_needs_no_baseline():
    lockbox = Dataset(np.zeros((3, 16)), np.array([0.2, 0.3, 0.4]), np.arange(3), FEATURE_NAMES)

    out = brier_breakdown(lockbox, np.full(3, 0.3), np.full(3, 0.3), np.full(3, 0.3), base=0.3)

    assert set(out) == {"label_between_0_and_1"}


# ---------------------------------------------------------------- L6: the append-only log
def test_every_scoring_is_appended_and_counted(tmp_path):
    log = tmp_path / "runs" / "lockbox_log.jsonl"

    first = append_log(log, {"run_id": "a", "lockbox_brier": 0.1})
    second = append_log(log, {"run_id": "b", "lockbox_brier": 0.2})

    assert (first, second) == (1, 2)
    lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert [x["run_id"] for x in lines] == ["a", "b"] and [x["scoring"] for x in lines] == [1, 2]


# ---------------------------------------------------------------- L1: coefficient signs
def test_the_logistic_coefficients_are_compared_with_the_monotone_directions():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(500, len(FEATURE_NAMES)))
    up = FEATURE_NAMES.index("instalment_to_income")
    y = 1 / (1 + np.exp(-2.0 * x[:, up]))
    fitted = fit_soft("logistic", {}, x, y, FEATURE_NAMES)

    rows = logistic_sign_check(fitted)

    assert [r["feature"] for r in rows] == list(FEATURE_NAMES)
    by_name = {r["feature"]: r for r in rows}
    assert (
        by_name["instalment_to_income"]["direction"] == MONOTONE_DIRECTIONS["instalment_to_income"]
    )
    assert by_name["instalment_to_income"]["coefficient"] > 0
    free = [r for r in rows if r["direction"] == 0]
    assert all(r["agrees"] is None for r in free)  # no expected sign, no verdict
    constrained = [r for r in rows if r["direction"] != 0]
    assert all(isinstance(r["agrees"], bool) for r in constrained)


def test_each_lockbox_counts_its_own_scorings(tmp_path):
    """Engine v3: a line without a lockbox tag scored the every-tenth lockbox, as the continuity
    lines do; the new lockbox is counted apart."""
    log = tmp_path / "lockbox_log.jsonl"
    assert append_log(log, {"run_id": "v2"}) == 1
    assert append_log(log, {"run_id": "v3", "lockbox": "new"}) == 1
    assert append_log(log, {"run_id": "v3", "lockbox": "old (continuity)"}) == 2
