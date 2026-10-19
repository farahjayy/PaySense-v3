"""The v1/v2 comparison and the bias-term sensitivity read only what other scripts wrote."""

import json

import pytest

from ml.engine2_train.compare_versions import (
    bias_sensitivity,
    buffer_effect,
    decide_engine2,
    label_facts,
    model_facts,
    paired_change,
    read_labels,
    render,
)


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def row(index, label, p_without, buffer=0.0, persona="frequent_bnpl", locked=False):
    if locked:
        return {"index": index, "locked": True}
    return {
        "index": index,
        "locked": False,
        "label": label,
        "p_without": p_without,
        "features": {"savings_buffer_to_income": buffer},
        "truth": {"persona": persona},
    }


def test_locked_profiles_are_left_out(tmp_path):
    labels = read_labels(write(tmp_path / "a.jsonl", [row(0, 0.5, 0.2), row(1, 0, 0, locked=True)]))
    assert list(labels) == [0]


def test_label_facts_count_saturation_and_the_baseline(tmp_path):
    labels = read_labels(
        write(tmp_path / "a.jsonl", [row(0, 0.0, 0.0), row(1, 1.0, 0.95), row(2, 0.2, 0.05)])
    )
    facts = label_facts(labels)
    assert facts["share_label_exactly_0_or_1"] == 2 / 3
    assert facts["share_short_before_purchase"] == 1 / 3  # only 0.95 is at or above 0.10
    # profile 2 moves from Safe (0.05) to Caution (0.2): the purchase decided its band
    assert facts["share_band_decided_before_purchase"] == 2 / 3


def test_bias_sensitivity_pairs_students_and_counts_band_moves(tmp_path):
    main = read_labels(write(tmp_path / "m.jsonl", [row(0, 0.05, 0), row(1, 0.5, 0.4)]))
    centred = read_labels(write(tmp_path / "c.jsonl", [row(0, 0.15, 0), row(1, 0.5, 0.4)]))
    out = bias_sensitivity(main, centred)
    assert out["profiles"] == 2
    assert out["band_agreement"] == 0.5
    assert out["transitions"][("Safe", "Caution")] == 1
    assert abs(out["mean_change"] - 0.05) < 1e-12


def test_buffer_effect_splits_students_by_whether_v2_gave_a_buffer(tmp_path):
    v1 = read_labels(write(tmp_path / "1.jsonl", [row(0, 0.6, 0.5), row(1, 0.6, 0.5)]))
    v2 = read_labels(write(tmp_path / "2.jsonl", [row(0, 0.1, 0.05, buffer=2.0), row(1, 0.7, 0.6)]))
    out = buffer_effect(v1, v2)
    assert out["with a buffer"]["mean_label_v2"] == 0.1
    assert out["no buffer"]["mean_label_v2"] == 0.7


def test_the_page_says_it_is_generated_and_discloses_the_second_lockbox_scoring(tmp_path):
    labels = read_labels(write(tmp_path / "a.jsonl", [row(0, 0.5, 0.2)]))
    page = render(
        {"v1": label_facts(labels), "v2": label_facts(labels)},
        bias_sensitivity(labels, labels),
        buffer_effect(labels, labels),
    )
    assert "do not edit by hand" in page
    assert "scored once for v1" in page


def test_the_lockbox_skill_score_is_comparable_across_label_versions(tmp_path):
    """ml-audit M3: raw Brier scores on different labels do not compare; 1 - B / B_const does."""
    meta = {"metrics": {"lockbox_calibrated": {"brier": 0.02}, "lockbox_constant_brier": 0.2}}
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(meta), encoding="utf-8")
    assert model_facts(path)["lockbox_brier_skill"] == pytest.approx(0.9)


# --- engine v3 (plan 2026-10-18-engine-v3 §5.4) ---
V2 = {"lockbox_brier_skill": 0.9153, "serving_band_agreement": 0.92}


def _v3(skill=0.95, brier=0.006, p_without=0.04, serving=0.95):
    return {
        "lockbox_brier_skill": skill,
        "lockbox_brier_calibrated": brier,
        "lockbox_brier_p_without": p_without,
        "serving_band_agreement": serving,
    }


def test_engine2_v3_is_served_only_when_all_three_criteria_hold():
    assert decide_engine2(V2, _v3())["serve"] is True


@pytest.mark.parametrize(
    "v3, failing",
    [(_v3(skill=0.91), 1), (_v3(brier=0.05), 2), (_v3(serving=0.899), 3)],
)
def test_each_engine2_criterion_can_hold_v3_back(v3, failing):
    verdict = decide_engine2(V2, v3)
    assert verdict["serve"] is False
    assert [c["id"] for c in verdict["criteria"] if not c["holds"]] == [failing]


def test_a_missing_number_fails_its_criterion_instead_of_passing():
    v3 = _v3()
    del v3["serving_band_agreement"]
    assert decide_engine2(V2, v3)["serve"] is False


def test_paired_change_compares_the_same_students_across_versions(tmp_path):
    old = read_labels(write(tmp_path / "o.jsonl", [row(0, 0.05, 0.0), row(1, 0.5, 0.4)]))
    new = read_labels(write(tmp_path / "n.jsonl", [row(0, 0.15, 0.0), row(1, 0.5, 0.4),
                                                    row(10000, 0.2, 0.1)]))  # fmt: skip
    out = paired_change(old, new)
    assert out["profiles"] == 2 and out["band_agreement"] == 0.5
    assert out["mean_label_old"] == pytest.approx(0.275)


def test_the_page_has_a_v3_column_and_the_decision(tmp_path):
    labels = read_labels(write(tmp_path / "a.jsonl", [row(0, 0.5, 0.2)]))
    facts = {"v1": label_facts(labels), "v2": {**label_facts(labels), **V2},
             "v3": {**label_facts(labels), **_v3()}}  # fmt: skip
    page = render(
        facts, bias_sensitivity(labels, labels), buffer_effect(labels, labels),
        paired_change(labels, labels), decide_engine2(V2, _v3()),
    )  # fmt: skip
    assert "| measure | v1 | v2 | v3 |" in page
    assert "## Serve rule for v3" in page and "v3 is served" in page
