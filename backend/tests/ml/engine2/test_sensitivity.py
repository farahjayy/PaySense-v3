import numpy as np

from app.engines.risk.features import FEATURE_NAMES
from ml.engine2_train.cv import cross_validate
from ml.engine2_train.data import Dataset
from ml.engine2_train.sensitivity import learning_curve, monotonicity_cost, shortfall_definition
from tests.ml.engine2.test_train import synthetic


def test_a_learning_curve_grows_the_training_set_and_scores_the_same_test_folds():
    data = synthetic(300)

    curve = learning_curve("logistic", data, {}, folds=3, seed=0, fractions=(0.25, 0.5, 1.0))

    assert [c["fraction"] for c in curve] == [0.25, 0.5, 1.0]
    sizes = [c["train_profiles"] for c in curve]
    assert sizes == sorted(sizes) and sizes[-1] == 200  # two thirds of 300
    assert all(np.isfinite(c["brier"]) and c["brier_se"] >= 0 for c in curve)
    assert curve[-1]["brier"] <= curve[0]["brier"] + 0.01  # more data does not hurt much


def test_the_cost_of_monotonicity_is_measured_with_both_arms_computed_fresh_on_the_same_folds():
    data = synthetic(240)

    out = monotonicity_cost("xgboost", data, 1, 3, 2, 0)

    again = cross_validate("xgboost", data, 1, 3, trials=2, seed=0)  # what the constrained arm is
    free = cross_validate("xgboost", data, 1, 3, trials=2, seed=0, constrained=False)
    assert out["applicable"] and out["brier_constrained"] == again.mean("brier")
    assert out["brier_unconstrained"] == free.mean("brier")
    assert out["delta_ci"][0] <= out["delta_brier"] <= out["delta_ci"][1]
    assert np.isfinite(out["brier_unconstrained"]) and 0 <= out["p"] <= 1


def test_the_logistic_benchmark_has_nothing_to_unconstrain():
    data = synthetic(120)

    assert monotonicity_cost("logistic", data, 1, 3, 0, 0)["applicable"] is False


def test_the_per_month_definition_is_compared_with_the_cumulative_one():
    base = synthetic(100)
    monthly = np.clip(base.y * 0.8, 0, 1)
    data = Dataset(base.x, base.y, base.index, FEATURE_NAMES, label_monthly=monthly)
    oof = base.y.copy()

    out = shortfall_definition(oof, data)

    assert out["available"] and out["brier_vs_cumulative"] == 0.0
    assert out["brier_vs_monthly"] > 0
    assert out["mean_label_monthly"] < out["mean_label_cumulative"]
    assert np.array(out["band_confusion_cumulative_rows_monthly_columns"]).sum() == 100


def test_without_a_per_month_label_the_sensitivity_says_so_rather_than_inventing_one():
    assert shortfall_definition(np.zeros(5), synthetic(5))["available"] is False
