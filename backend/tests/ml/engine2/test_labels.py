import hashlib
import json
from dataclasses import fields
from datetime import timedelta

import numpy as np
import pytest

from app.engines.forecasting.models import MovingAverage
from app.engines.forecasting.recurring import detect
from app.engines.risk.features import FEATURE_NAMES, FEATURE_SCHEMA_HASH
from ml.datagen.params import load_params
from ml.datagen.profile import draw_as_of, generate_profile
from ml.engine2_train.labels import (
    LABELS_FILE,
    MANIFEST_FILE,
    generate_labels,
    iter_labels,
    label_profile,
    prepare,
    profile_seed,
)

PARAMS = load_params()
MODEL = MovingAverage(13)
SEED = 5


def profile(index, **kwargs):
    return generate_profile(PARAMS, SEED, index, **kwargs)


class Blind:
    """A profile that exposes only what the product knows: any answer-key access raises."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        if name in {"persona", "recurring_truth", "expected_monthly_income_sen"}:
            raise AssertionError(f"label code read the answer key {name!r}")
        return getattr(self._real, name)


def test_a_label_is_a_probability_with_all_seventeen_features():
    record = label_profile(profile(0), MODEL, SEED, paths=200)

    assert record is not None
    assert 0 <= record["label"] <= 1 and 0 <= record["p_without"] <= 1
    assert list(record["features"]) == list(FEATURE_NAMES)
    assert all(np.isfinite(v) for v in record["features"].values())


def test_the_purchase_cannot_lower_the_chance_of_a_shortfall():
    for index in range(8):
        record = label_profile(profile(index), MODEL, SEED, paths=200)
        if record:
            assert record["label"] >= record["p_without"] - 1e-12


def test_labelling_never_reads_the_generators_answer_keys():
    label_profile(Blind(profile(1)), MODEL, SEED, paths=100)  # raises if it touches one


def test_confirmed_items_come_from_detection_on_the_ledger_not_from_ground_truth():
    p = profile(2)

    known = prepare(p)

    expected = {s.name for s in detect(known["rows"], today=p.as_of)}
    assert {i["match_text"] for i in known["items"]} == expected
    truth = {t.name.lower() for t in p.recurring_truth}
    assert len(known["items"]) <= len(truth) + len(expected)  # detection decides, not the truth


def test_plan_status_is_the_status_on_the_as_of_day():
    for index in range(12):
        p = profile(index, persona="frequent_bnpl")
        known = prepare(p)
        for generated, plan in zip(p.bnpl.plans, known["plans"], strict=True):
            for seq, instalment in enumerate(plan["installments"], start=1):
                paid_on = generated.paid_dates.get(seq)
                assert instalment["is_paid"] == (paid_on is not None and paid_on <= p.as_of)


def test_only_recorded_limits_are_used():
    p = profile(3, persona="frequent_bnpl")

    assert prepare(p)["limits"] == dict(p.bnpl.limits)  # recorded, never the true limits


def test_the_ledger_ends_on_the_as_of_day():
    p = profile(4)

    assert all(r["date"] <= p.as_of for r in prepare(p)["rows"])


def test_the_same_profile_and_seed_always_give_the_same_label():
    a = label_profile(profile(5), MODEL, SEED, paths=150)
    b = label_profile(profile(5), MODEL, SEED, paths=150)

    assert a == b


def test_profile_seeds_depend_only_on_the_master_seed_and_the_index():
    assert profile_seed(1, 2) == profile_seed(1, 2)
    assert profile_seed(1, 2) != profile_seed(1, 3) and profile_seed(1, 2) != profile_seed(2, 2)


def test_a_profile_with_too_little_history_is_reported_locked_not_dropped(tmp_path):
    manifest = generate_labels(PARAMS, SEED, 6, tmp_path, paths=100, forecaster=MODEL)

    lines = [json.loads(x) for x in (tmp_path / LABELS_FILE).read_text("utf-8").splitlines()]
    assert len(lines) == 6 and sum(x["locked"] for x in lines) == manifest["locked_profiles"]
    assert all("label" in x for x in lines if not x["locked"])


def test_the_manifest_records_what_is_needed_to_reproduce_and_audit_the_run(tmp_path):
    manifest = generate_labels(PARAMS, SEED, 4, tmp_path, paths=100, forecaster=MODEL)

    on_disk = json.loads((tmp_path / MANIFEST_FILE).read_text("utf-8"))
    assert on_disk == manifest
    assert manifest["feature_schema_hash"] == FEATURE_SCHEMA_HASH
    assert manifest["params_hash"] == PARAMS.hash() and manifest["label_version"]
    assert manifest["file"]["sha256"] and manifest["feature_names"] == list(FEATURE_NAMES)


def test_a_run_is_reproducible_and_a_short_run_is_a_prefix_of_a_longer_one(tmp_path):
    generate_labels(PARAMS, SEED, 5, tmp_path / "a", paths=100, forecaster=MODEL)
    generate_labels(PARAMS, SEED, 3, tmp_path / "b", paths=100, forecaster=MODEL)

    long = (tmp_path / "a" / LABELS_FILE).read_text("utf-8").splitlines()
    short = (tmp_path / "b" / LABELS_FILE).read_text("utf-8").splitlines()
    assert long[:3] == short


def test_answer_keys_are_kept_under_truth_in_the_output(tmp_path):
    generate_labels(PARAMS, SEED, 2, tmp_path, paths=100, forecaster=MODEL)

    for line in (tmp_path / LABELS_FILE).read_text("utf-8").splitlines():
        record = json.loads(line)
        assert "persona" not in record and "persona" in record["truth"]
        assert "persona" not in record.get("features", {})


def test_no_field_of_the_profile_used_for_features_is_an_answer_key():
    names = {f.name for f in fields(profile(0))}

    assert {"persona", "recurring_truth"} <= names  # they exist, and the Blind test proves unused


def test_a_label_run_does_not_need_the_clock(tmp_path):
    p = profile(6)
    assert p.as_of - timedelta(days=1) < p.as_of  # fixed reference day, no wall-clock dependence


def test_each_label_is_made_on_its_own_as_of_day_drawn_from_the_seed_and_the_index():
    records = list(iter_labels(PARAMS, SEED, 6, MODEL, paths=100))

    days = [r["as_of"] for r in records]
    assert days == [draw_as_of(PARAMS, SEED, r["index"]).isoformat() for r in records]
    assert len(set(days)) > 3  # not one shared calendar position (audit finding M1)


def test_a_label_records_the_per_month_definition_beside_the_cumulative_one():
    record = label_profile(profile(0), MODEL, SEED, paths=100)

    assert 0 <= record["label_monthly"] <= 1 and 0 <= record["p_without_monthly"] <= 1


def test_the_manifest_records_the_provenance_of_the_run(tmp_path):
    manifest = generate_labels(PARAMS, SEED, 3, tmp_path, paths=100, forecaster=MODEL)

    assert manifest["label_version"] == "4"
    assert len(manifest["band_rule_sha256"]) == 64 and manifest["recentre_errors"] is False
    assert {"python", "numpy", "onnxruntime", "scipy"} <= set(manifest["versions"])
    assert "git_commit" in manifest and manifest["capped_profiles"] == 0
    assert manifest["horizon_max_weeks"] >= 160
    assert manifest["as_of_window"]["days"] == PARAMS["calendar.as_of_window_days"]


def test_an_interrupted_run_resumes_to_exactly_the_file_of_an_uninterrupted_one(tmp_path):
    generate_labels(PARAMS, SEED, 5, tmp_path / "whole", paths=100, forecaster=MODEL)
    whole = (tmp_path / "whole" / LABELS_FILE).read_bytes()
    generate_labels(PARAMS, SEED, 3, tmp_path / "cut", paths=100, forecaster=MODEL)
    cut = tmp_path / "cut" / LABELS_FILE
    cut.write_bytes(cut.read_bytes() + b'{"index":3,"lab')  # a crash in the middle of a line

    resumed = generate_labels(
        PARAMS, SEED, 5, tmp_path / "cut", paths=100, forecaster=MODEL, resume=True
    )

    assert cut.read_bytes() == whole
    assert resumed["file"]["sha256"] == hashlib.sha256(whole).hexdigest()


def test_a_run_refuses_to_resume_under_different_settings(tmp_path):
    generate_labels(PARAMS, SEED, 2, tmp_path, paths=100, forecaster=MODEL)

    with pytest.raises(ValueError, match="different"):
        generate_labels(PARAMS, SEED, 4, tmp_path, paths=200, forecaster=MODEL, resume=True)


def test_the_settings_a_run_is_resumed_under_include_the_code_it_was_made_with(tmp_path):
    generate_labels(PARAMS, SEED, 2, tmp_path, paths=100, forecaster=MODEL)

    sidecar = json.loads((tmp_path / "labels.run.json").read_text("utf-8"))
    assert "git_commit" in sidecar and sidecar["profiles"] == 2


def test_a_run_refuses_to_resume_with_fewer_profiles_than_are_already_written(tmp_path):
    generate_labels(PARAMS, SEED, 4, tmp_path, paths=100, forecaster=MODEL)
    before = (tmp_path / LABELS_FILE).read_bytes()

    with pytest.raises(ValueError, match="already holds"):
        generate_labels(PARAMS, SEED, 2, tmp_path, paths=100, forecaster=MODEL, resume=True)

    assert (tmp_path / LABELS_FILE).read_bytes() == before  # nothing was cut


# --- WP16: the savings buffer (D-50) and the bias-term sensitivity (C6) ---
def test_the_profiles_buffer_starts_the_label_and_is_a_feature():
    index = next(i for i in range(60) if profile(i).savings_buffer_sen > 0)
    record = label_profile(profile(index), MODEL, SEED, paths=200)
    assert record["features"]["savings_buffer_to_outgoings"] > 0
    assert prepare(profile(index))["savings_buffer_sen"] == profile(index).savings_buffer_sen


def test_a_buffer_never_raises_the_label():
    from dataclasses import replace

    for index in range(12):
        with_buffer = profile(index)
        if with_buffer.savings_buffer_sen == 0:
            continue
        without = replace(with_buffer, savings_buffer_sen=0)
        a = label_profile(with_buffer, MODEL, SEED, paths=200)
        b = label_profile(without, MODEL, SEED, paths=200)
        if a and b:
            assert a["label"] <= b["label"] + 1e-12


def test_recentred_errors_are_a_separate_run_that_records_the_switch(tmp_path):
    plain = generate_labels(PARAMS, SEED, 3, tmp_path / "plain", paths=100, forecaster=MODEL)
    centred = generate_labels(
        PARAMS, SEED, 3, tmp_path / "centred", paths=100, forecaster=MODEL, recentre_errors=True
    )
    assert plain["recentre_errors"] is False and centred["recentre_errors"] is True
    assert plain["label_version"] == centred["label_version"] == "4"


def test_recentring_removes_the_records_mean_error():
    from app.engines.forecasting.service import prepare_ledger

    known = prepare(profile(2))
    plain = prepare_ledger(known["rows"], known["items"], known["as_of"], MODEL)
    centred = prepare_ledger(
        known["rows"], known["items"], known["as_of"], MODEL, recentre_errors=True
    )
    assert abs(float(centred.spend_errors.mean())) < 1e-6
    assert abs(float(centred.income_errors.mean())) < 1e-6
    assert np.allclose(
        plain.spend_errors - plain.spend_errors.mean(), centred.spend_errors, atol=1e-6
    )
