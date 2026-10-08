import json

import numpy as np

from app.engines.risk.features import ENGINE1_FEATURES, FEATURE_NAMES
from ml.engine2_train.models import CANDIDATES
from ml.engine2_train.train import CONFIGS, TrainConfig, run


def write_labels(path, n=360, seed=0):
    rng = np.random.default_rng(seed)
    lines = []
    for i in range(n):
        x = rng.normal(size=len(FEATURE_NAMES))
        up = x[FEATURE_NAMES.index("instalment_to_income")]
        down = x[FEATURE_NAMES.index("margin_monthly_p50_without")]
        label = float(
            np.clip(1 / (1 + np.exp(-(1.8 * up - 1.5 * down))) + rng.normal(0, 0.05), 0, 1)
        )
        lines.append(
            {"index": i, "locked": False, "label": label,
             "features": dict(zip(FEATURE_NAMES, x.tolist(), strict=True)),
             "truth": {"persona": "x"}}
        )  # fmt: skip
    path.write_text("\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")


TINY = TrainConfig("tiny", repeats=2, folds=3, trials=2)


def test_the_shipped_configurations_use_the_pre_registered_cv_shape():
    assert CONFIGS["full"].repeats == 5 and CONFIGS["full"].folds == 5
    assert CONFIGS["small"].folds == 3


def test_a_run_compares_all_four_candidates_and_records_what_is_needed_to_audit_it(tmp_path):
    write_labels(tmp_path / "labels.jsonl")

    record = run(TINY, tmp_path / "labels.jsonl", tmp_path / "out")

    assert set(record["models"]) == set(CANDIDATES)
    assert record["winner"] in CANDIDATES and record["reason"]
    assert record["calibration"]["chosen"] in {"none", "platt", "isotonic"}
    assert record["models"][record["winner"]]["brier_mean"] < record["constant_baseline_brier"]
    saved = json.loads((tmp_path / "out" / "results.json").read_text(encoding="utf-8"))
    assert saved["feature_schema_hash"] == record["feature_schema_hash"]
    assert saved["models"]["logistic"]["folds"] == 6


def test_the_ablation_removes_exactly_the_engine_one_features(tmp_path):
    write_labels(tmp_path / "labels.jsonl")

    record = run(TINY, tmp_path / "labels.jsonl", tmp_path / "out")

    assert record["ablation"]["removed_features"] == list(ENGINE1_FEATURES)
    assert len(record["ablation"]["delta_ci"]) == 2
    assert record["ablation"]["delta_ci"][0] <= record["ablation"]["delta_brier"]
    assert record["ablation"]["delta_brier"] <= record["ablation"]["delta_ci"][1]


def test_a_run_is_reproducible(tmp_path):
    write_labels(tmp_path / "labels.jsonl")

    a = run(TINY, tmp_path / "labels.jsonl", tmp_path / "a")
    b = run(TINY, tmp_path / "labels.jsonl", tmp_path / "b")

    assert a["models"]["logistic"]["brier_mean"] == b["models"]["logistic"]["brier_mean"]
    assert a["winner"] == b["winner"] and a["final_params"] == b["final_params"]
