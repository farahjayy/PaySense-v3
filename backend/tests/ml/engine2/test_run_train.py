import json

import numpy as np
import pytest
from scipy import stats

from app.engines.risk.features import ENGINE1_FEATURES, FEATURE_NAMES
from ml.engine2_train import report, train
from ml.engine2_train.cv import cross_validate
from ml.engine2_train.data import LOW_BASELINE, load_labels, split_lockbox
from ml.engine2_train.models import CANDIDATES
from ml.engine2_train.provenance import sha256_file
from ml.engine2_train.train import CONFIGS, TrainConfig, run

TINY = TrainConfig("tiny", repeats=2, folds=3, trials=2)
PROFILES = 360


def write_labels(path, n=PROFILES, seed=0, scramble_lockbox=False, capped=False):
    rng = np.random.default_rng(seed)
    lines = []
    for i in range(n):
        x = rng.normal(size=len(FEATURE_NAMES))
        up = x[FEATURE_NAMES.index("instalment_to_income")]
        down = x[FEATURE_NAMES.index("margin_monthly_p50_without")]
        label = float(
            np.clip(1 / (1 + np.exp(-(1.8 * up - 1.5 * down))) + rng.normal(0, 0.05), 0, 1)
        )
        base = float(label * rng.uniform(0, 1))
        if scramble_lockbox and i % 10 == 0:
            label = 1.0 - label  # wreck every lockbox label
        lines.append(
            {"index": i, "locked": False, "label": label, "p_without": base,
             "horizon_capped": capped and i == 3, "label_monthly": float(label * 0.9),
             "features": dict(zip(FEATURE_NAMES, x.tolist(), strict=True)),
             "truth": {"persona": "x" if i % 2 else "y", "price_to_income": 0.1 + i / 100}}
        )  # fmt: skip
    path.write_text("\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    """One shared run: every test below only reads it."""
    root = tmp_path_factory.mktemp("tiny")
    write_labels(root / "labels.jsonl")
    record = run(TINY, root / "labels.jsonl", root / "run")
    return root, record


def test_the_shipped_configurations_use_the_pre_registered_cv_shape():
    assert CONFIGS["full"].repeats == 5 and CONFIGS["full"].folds == 5
    assert CONFIGS["small"].folds == 3


def test_a_run_compares_all_four_candidates_and_records_what_is_needed_to_audit_it(tiny):
    root, record = tiny

    assert set(record["models"]) == set(CANDIDATES)
    assert record["winner"] in CANDIDATES and record["reason"]
    assert record["calibration"]["chosen"] in {"none", "platt", "isotonic"}
    assert record["models"][record["winner"]]["brier_mean"] < record["constant_baseline_brier"]
    saved = json.loads((root / "run" / "results.json").read_text(encoding="utf-8"))
    assert saved["feature_schema_hash"] == record["feature_schema_hash"]
    assert saved["models"]["logistic"]["folds"] == 6


def test_every_tenth_profile_is_a_lockbox_that_no_selection_step_sees(tiny):
    _, record = tiny

    assert record["lockbox_profiles"] == 36 and record["development_profiles"] == 324
    box = record["lockbox"]
    assert box["profiles"] == 36 and record["strata"] == 10
    assert box["constant_brier"] > 0 and box["logistic_benchmark_brier"] > 0
    assert "brier" in box["calibrated"] and "brier" in box["raw"]
    assert 0 <= box["band_agreement"] <= 1
    assert sum(sum(r) for r in box["band_confusion_label_rows_model_columns"]) == 36
    assert LOW_BASELINE in box["subgroups"]
    facts = record["label_facts"]["development"]
    assert 0 <= facts["share_purchase_moves_the_band"] <= 1  # how much the purchase matters
    assert record["label_facts"]["all"]["share_p_without_exactly_1"] >= 0


def test_the_lockbox_labels_cannot_change_anything_chosen_before_it_is_scored(tiny, tmp_path):
    _, a = tiny
    write_labels(tmp_path / "b.jsonl", scramble_lockbox=True)

    b = run(TINY, tmp_path / "b.jsonl", tmp_path / "rb")

    assert a["winner"] == b["winner"] and a["final_params"] == b["final_params"]
    assert a["calibration"] == b["calibration"] and a["ablation"] == b["ablation"]
    assert a["models"]["logistic"]["brier_mean"] == b["models"]["logistic"]["brier_mean"]
    assert a["lockbox"]["calibrated"]["brier"] != b["lockbox"]["calibrated"]["brier"]


def test_the_calibrator_is_fitted_on_single_repeat_out_of_fold_predictions_and_stored(tiny):
    root, record = tiny

    assert record["calibration"]["fitted_on"].startswith("single-repeat out-of-fold")
    stored = json.loads((root / "run" / "calibrator.json").read_text(encoding="utf-8"))
    assert stored == record["calibration"]["parameters"]
    assert stored["kind"] == record["calibration"]["chosen"]
    assert (root / "run" / "final_model.joblib").is_file()
    assert np.load(root / "run" / "oof_winner.npy").shape == (324,)


def test_a_run_records_what_it_was_made_with(tiny):
    root, record = tiny

    versions = {"scikit-learn", "lightgbm", "optuna", "scipy", "xgboost", "onnxruntime", "torch"}
    assert versions <= set(record["versions"])
    assert record["labels_sha256"] == sha256_file(root / "labels.jsonl")
    assert "git_commit" in record


def test_the_ablation_uses_nested_tuning_in_both_arms_and_the_t_critical_value(tiny):
    _, record = tiny

    ablation = record["ablation"]
    assert "nested" in ablation["tuning"] and LOW_BASELINE in ablation["subgroups"]
    assert ablation["removed_features"] == list(ENGINE1_FEATURES)
    low, high = ablation["delta_ci"]
    assert low <= ablation["delta_brier"] <= high
    j = record["models"][record["winner"]]["folds"]  # 6 folds: t(5) = 2.57, not 1.96
    assert stats.t.ppf(0.975, j - 1) / 1.96 > 1.3 and (high - low) > 0


def test_the_sensitivity_runs_are_in_the_record(tiny):
    _, record = tiny

    sensitivity = record["sensitivity"]
    assert len(sensitivity["learning_curve"]) == 5
    assert sensitivity["shortfall_definition"]["available"]
    assert "applicable" in sensitivity["monotonicity"]


def test_a_run_is_reproducible(tiny, tmp_path):
    root, a = tiny

    b = run(TINY, root / "labels.jsonl", tmp_path / "b")

    assert a["models"]["logistic"]["brier_mean"] == b["models"]["logistic"]["brier_mean"]
    assert a["winner"] == b["winner"] and a["final_params"] == b["final_params"]
    assert a["lockbox"] == b["lockbox"]


# ---------------------------------------------------------------- audit M1-M3, L1, L6
def test_both_arms_of_the_ablation_and_of_the_monotonicity_run_are_fresh_on_fresh_folds(tiny):
    root, record = tiny
    dev, _ = split_lockbox(load_labels(root / "labels.jsonl"))
    fresh = TINY.seed + train.FRESH_FOLDS_OFFSET
    winner = record["winner"]

    with_engine1 = cross_validate(winner, dev, TINY.repeats, TINY.folds, TINY.trials, fresh)

    assert record["ablation"]["brier_with_engine1"] == with_engine1.mean("brier")
    assert record["ablation"]["fresh_folds_seed"] == fresh
    mono = record["sensitivity"]["monotonicity"]
    if mono["applicable"]:
        assert mono["brier_constrained"] == with_engine1.mean("brier")
        assert mono["fresh_folds_seed"] == fresh


def test_the_lockbox_record_carries_the_subgroup_in_full_and_the_label_class_breakdown(tiny):
    _, record = tiny

    box = record["lockbox"]
    group = box["subgroups"][LOW_BASELINE]
    assert {"band_agreement", "reliability", "constant_value", "raw", "calibrated"} <= set(group)
    assert group["constant_basis"].startswith("development mean of the subgroup")
    classes = box["brier_by_class"]
    assert {"label_exactly_0", "label_between_0_and_1", "p_without_between_0_and_1"} <= set(classes)
    json.dumps(box, allow_nan=False)


def test_every_lockbox_scoring_is_logged_and_counted_in_the_record(tiny, tmp_path):
    root, record = tiny
    log = root / "lockbox_log.jsonl"

    lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]

    assert record["lockbox_scorings"] == len(lines) == 1
    assert lines[0]["winner"] == record["winner"]
    assert lines[0]["labels_sha256"] == record["labels_sha256"]
    assert lines[0]["lockbox_brier_calibrated"] == record["lockbox"]["calibrated"]["brier"]
    assert {"run_id", "git_commit", "scoring"} <= set(lines[0])
    again = run(TINY, root / "labels.jsonl", tmp_path / "again")
    assert again["lockbox_scorings"] == 1  # its own log, beside its own output
    second = run(TINY, root / "labels.jsonl", tmp_path / "again")
    assert second["lockbox_scorings"] == 2


def test_a_run_that_fails_before_the_lockbox_has_not_used_it(tmp_path, monkeypatch):
    write_labels(tmp_path / "labels.jsonl")

    def boom(*_args, **_kwargs):
        raise RuntimeError("ablation failed")

    monkeypatch.setattr(train, "_ablation", boom)
    with pytest.raises(RuntimeError):
        run(TINY, tmp_path / "labels.jsonl", tmp_path / "run")

    assert not (tmp_path / "lockbox_log.jsonl").exists()


def test_the_logistic_signs_against_the_monotone_directions_are_recorded(tiny):
    _, record = tiny

    signs = record["logistic_signs"]
    assert [r["feature"] for r in signs["features"]] == list(FEATURE_NAMES)
    assert signs["agree"] + signs["disagree"] == signs["constrained_features"]
    assert record["served_model_has_monotone_constraints"] == (record["winner"] != "logistic")


def test_the_constants_serving_will_need_are_copied_into_the_record(tiny):
    _, record = tiny

    constants = record["serving_constants"]
    assert set(constants) == {
        "RISK_CHECK_MAX_WEEKS", "DASHBOARD_MONTHS", "ERROR_INFLATION", "BOOTSTRAP_BLOCK"
    }  # fmt: skip
    assert constants["RISK_CHECK_MAX_WEEKS"] >= 160
    assert {"label_version", "horizon_max_weeks", "served_model_files"} <= set(
        record["labels_manifest"]
    )


# ---------------------------------------------------------------- the report
def test_the_report_is_built_from_a_stored_run_and_states_what_it_computed(tiny, tmp_path):
    root, record = tiny

    report.build_report(root / "run", tmp_path / "out", root / "labels.jsonl")

    readme = (tmp_path / "out" / "README.md").read_text(encoding="utf-8")
    assert "distils Engine 1" in readme and "Winner:" in readme
    assert "untouched lockbox" in readme and "## Not done" in readme
    assert "Allowances were corrected once" not in readme  # the hard-coded sentence is gone
    assert "mostly measures" in readme and "moves the band" in readme
    assert "truncated for 0 of" in readme  # the horizon statement is generated, not assumed
    assert "quantile bins" in readme and "deciles" not in readme.lower()
    tables = ("cv_metrics", "label_bands", "label_baseline", "ablation", "calibration", "lockbox",
              "learning_curve", "label_by_persona", "label_by_price_ratio")  # fmt: skip
    for name in tables:
        assert (tmp_path / "out" / "tables" / f"{name}.csv").is_file(), name
    cv = (tmp_path / "out" / "tables" / "cv_metrics.csv").read_text(encoding="utf-8")
    assert "logistic" in cv and "constant" in cv  # the benchmark and the baseline are always there
    ablation = (tmp_path / "out" / "tables" / "ablation.csv").read_text(encoding="utf-8")
    assert LOW_BASELINE in ablation  # the subgroup is reported beside the whole
    assert record["winner"] in readme
    assert "reported separately everywhere" not in readme  # said exactly where it appears instead
    assert "Brier by label class" in readme and "exactly 0" in readme
    assert "coefficient" in readme and "no monotone constraints" in readme
    assert "fitted on out-of-fold predictions of the fold models" in readme
    assert "Shapley" in readme and "same scale" in readme
    assert "raw scale" not in readme
    assert "scored 1 time" in readme  # the lockbox log, in words
    assert "the six Engine 1 features" not in readme  # the count comes from the record
    for name in ("lockbox_by_class", "lockbox_subgroup", "logistic_signs"):
        assert (tmp_path / "out" / "tables" / f"{name}.csv").is_file(), name


def test_the_report_regenerates_identically(tiny, tmp_path):
    root, _ = tiny

    report.build_report(root / "run", tmp_path / "a", root / "labels.jsonl")
    report.build_report(root / "run", tmp_path / "b", root / "labels.jsonl")

    for name in ("README.md", "tables/cv_metrics.csv", "tables/ablation.csv", "tables/lockbox.csv"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_the_report_refuses_labels_other_than_the_ones_the_run_used(tiny, tmp_path):
    root, _ = tiny
    write_labels(tmp_path / "other.jsonl", seed=99)

    with pytest.raises(ValueError, match="not the file this run was trained on"):
        report.build_report(root / "run", tmp_path / "out", tmp_path / "other.jsonl")


def test_the_report_refuses_a_label_file_with_a_truncated_horizon(tiny, tmp_path):
    root, _ = tiny
    write_labels(tmp_path / "capped.jsonl", capped=True)
    stored = json.loads((root / "run" / "results.json").read_text(encoding="utf-8"))
    stored["labels_sha256"] = sha256_file(tmp_path / "capped.jsonl")
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "results.json").write_text(json.dumps(stored), encoding="utf-8")

    with pytest.raises(ValueError, match="truncated horizon"):
        report.build_report(tmp_path / "run", tmp_path / "out", tmp_path / "capped.jsonl")


def test_the_report_reads_the_manifest_that_sits_beside_its_labels(tiny, tmp_path):
    root, _ = tiny
    labels = tmp_path / "labels.jsonl"
    labels.write_bytes((root / "labels.jsonl").read_bytes())
    manifest = {"file": {"sha256": "not-this-file"}, "paths": 1000}
    (tmp_path / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="does not describe the labels"):
        report.build_report(root / "run", tmp_path / "out", labels)
