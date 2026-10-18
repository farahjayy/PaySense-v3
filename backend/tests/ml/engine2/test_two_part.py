"""G1 (engine v3, D-62): the two-part target p_with = b + (1 - b) * q, trained on q with weight
(1 - b), every score on the composed probability; the new lockbox and the old one as continuity."""

import json

import numpy as np
import pytest

from app.engines.risk.features import FEATURE_NAMES
from ml.engine2_train.calibrate import choose_calibration, fit_calibrator
from ml.engine2_train.data import (
    BASE_COLUMN,
    NEW_LOCKBOX_FROM,
    Dataset,
    continuity_lockbox,
    load_labels,
    split_lockbox,
)
from ml.engine2_train.models import fit_soft, logistic_sign_check, two_part_target
from ml.engine2_train.train import TrainConfig, run

TINY = TrainConfig("tiny", repeats=1, folds=3, trials=1)


def test_the_target_is_the_share_of_the_safe_paths_the_purchase_makes_short():
    y = np.array([0.5, 1.0, 0.2, 0.6])
    b = np.array([0.0, 1.0, 0.2, 0.2])
    q, w = two_part_target(y, b)
    np.testing.assert_allclose(q, [0.5, 0.0, 0.0, 0.5])
    np.testing.assert_allclose(w, [1.0, 0.0, 0.8, 0.8])
    q, _ = two_part_target(np.array([0.1]), np.array([0.2]))  # never negative
    assert q[0] == 0.0


def _data(n=300, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, len(FEATURE_NAMES)))
    b = np.clip(rng.uniform(-0.3, 1.2, n), 0, 1)
    q = 1 / (1 + np.exp(-2 * x[:, FEATURE_NAMES.index("instalment_to_income")]))
    y = b + (1 - b) * q
    return Dataset(x, y, np.arange(n), FEATURE_NAMES, p_without=b)


@pytest.mark.parametrize("name", ["logistic", "lightgbm"])
def test_a_two_part_model_composes_its_prediction_with_the_base(name):
    data = _data().with_base()
    assert data.names[-1] == BASE_COLUMN and data.x.shape[1] == len(FEATURE_NAMES) + 1
    fitted = fit_soft(name, {}, data.x, data.y, data.names, seed=0)
    assert fitted.two_part
    pred = fitted.predict(data.x)
    b = data.x[:, -1]
    assert np.all(pred >= b - 1e-12) and np.all(pred[b == 1] == 1.0)
    q = fitted.predict_q(data.x[:, :-1])
    np.testing.assert_allclose(pred, b + (1 - b) * q)
    assert np.corrcoef(q, _data().x[:, FEATURE_NAMES.index("instalment_to_income")])[0, 1] > 0.8


def test_the_logistic_signs_are_read_on_the_features_only():
    data = _data().with_base()
    rows = logistic_sign_check(fit_soft("logistic", {}, data.x, data.y, data.names))
    assert [r["feature"] for r in rows] == list(FEATURE_NAMES)


def test_calibration_on_q_is_weighted_and_scored_on_the_composed_probability():
    rng = np.random.default_rng(1)
    q = rng.uniform(0, 1, 400)
    b = rng.uniform(0, 1, 400)
    pred = np.clip(q + 0.2, 0, 1)  # q-hat biased up
    chosen, scores = choose_calibration(pred, q, seed=0, weight=1 - b, base=b)
    assert chosen in scores and scores[chosen] <= scores["none"]
    fitted = fit_calibrator("isotonic", pred, q, weight=1 - b)
    assert np.abs(fitted.apply(pred) - q).mean() < np.abs(pred - q).mean()


def test_the_new_lockbox_and_the_old_one_are_split_apart():
    index = np.r_[np.arange(0, 100), np.arange(NEW_LOCKBOX_FROM, NEW_LOCKBOX_FROM + 20)]
    data = Dataset(np.zeros((len(index), 1)), np.zeros(len(index)), index, ("a",))
    dev, box = split_lockbox(data)
    old = continuity_lockbox(data)
    assert set(box.index) == set(range(NEW_LOCKBOX_FROM, NEW_LOCKBOX_FROM + 20))
    assert set(old.index) == set(range(0, 100, 10))
    assert set(dev.index) == {i for i in range(100) if i % 10}
    # a label file without the new lockbox keeps the every-tenth rule and has no continuity part
    plain = Dataset(np.zeros((100, 1)), np.zeros(100), np.arange(100), ("a",))
    assert set(split_lockbox(plain)[1].index) == set(range(0, 100, 10))
    assert len(continuity_lockbox(plain)) == 0


def _write(path, indices, seed=0):
    rng = np.random.default_rng(seed)
    lines = []
    for i in indices:
        x = rng.normal(size=len(FEATURE_NAMES))
        b = float(np.clip(rng.uniform(-0.3, 1.1), 0, 1))
        q = float(1 / (1 + np.exp(-1.5 * x[FEATURE_NAMES.index("instalment_to_income")])))
        lines.append(
            {"index": int(i), "locked": False, "label": b + (1 - b) * q, "p_without": b,
             "horizon_capped": False, "label_monthly": b,
             "features": dict(zip(FEATURE_NAMES, x.tolist(), strict=True)),
             "truth": {"persona": "x", "price_to_income": 0.2}}
        )  # fmt: skip
    path.write_text("\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def two_part_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("twopart")
    indices = np.r_[np.arange(0, 300), np.arange(NEW_LOCKBOX_FROM, NEW_LOCKBOX_FROM + 40)]
    _write(root / "labels.jsonl", indices)
    return root, run(TINY, root / "labels.jsonl", root / "run")


def test_a_two_part_run_scores_the_new_lockbox_with_every_benchmark(two_part_run):
    root, record = two_part_run
    assert record["target"] == "two_part"
    assert record["lockbox_profiles"] == 40 and record["development_profiles"] == 270
    box = record["lockbox"]
    benchmarks = box["benchmarks"]
    assert {"constant", "logistic", "p_without", "p_without_plus_mean_q"} <= set(benchmarks)
    assert box["calibrated"]["brier"] < benchmarks["p_without"]["brier"]
    assert "purchase_moves_band" in box
    assert record["continuity"]["profiles"] == 30
    log = (root / "lockbox_log.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["lockbox"] for line in log] == ["new", "old (continuity)"]


def test_the_stored_run_reproduces_its_composed_lockbox_prediction(two_part_run):
    root, record = two_part_run
    from ml.engine2_train.train import calibrated_predict, load_run

    final, calibrator = load_run(root / "run")
    data = load_labels(root / "labels.jsonl").with_base()
    _, box = split_lockbox(data)
    pred = calibrated_predict(final, calibrator, box.x)
    brier = float(np.mean((pred - box.y) ** 2))
    assert brier == pytest.approx(record["lockbox"]["calibrated"]["brier"])
    assert np.all(pred >= box.p_without - 1e-12)


def test_a_two_part_model_exports_q_and_the_onnx_copy_matches_it():
    from ml.engine2_train.export import convert, model_output, parity

    data = _data().with_base()
    fitted = fit_soft("lightgbm", {}, data.x, data.y, data.names, seed=0)
    features = data.x[:, :-1]
    np.testing.assert_allclose(model_output(fitted, features), fitted.predict_q(features))
    found = parity(fitted, convert(fitted, len(FEATURE_NAMES)), features)
    assert found["max_abs_diff"] < 1e-3


def test_a_stress_run_gives_a_two_part_model_its_base_column():
    from ml.engine2_train.stress import VariantRun

    run_ = VariantRun(
        (1, 2), np.ones((2, 3)), np.array([0.5, 0.6]), 0, (True, True), np.array([0.2, 0.4])
    )
    assert run_.design().shape == (2, 3)
    np.testing.assert_allclose(run_.design(with_base=True)[:, -1], [0.2, 0.4])
    summary = run_.summary(lambda x: x[:, -1], with_base=True)
    assert summary["mean_prediction"] == pytest.approx(0.3)
