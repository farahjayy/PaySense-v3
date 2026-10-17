"""The v1/v2 comparison and the bias-term sensitivity read only what other scripts wrote."""

import json

from ml.engine2_train.compare_versions import (
    bias_sensitivity,
    buffer_effect,
    label_facts,
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
