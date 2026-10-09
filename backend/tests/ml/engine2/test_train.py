import json
import math

import numpy as np
import pytest

from app.engines.risk.features import FEATURE_NAMES, MONOTONE_DIRECTIONS
from ml.engine2_train.calibrate import Calibrator, choose_calibration, fit_calibrator
from ml.engine2_train.cv import CvResult, cross_validate, folds, nadeau_bengio
from ml.engine2_train.data import (
    LOCKBOX_EVERY,
    LOW_BASELINE,
    Dataset,
    load_labels,
    split_lockbox,
)
from ml.engine2_train.metrics import (
    all_metrics,
    auc_at_threshold,
    band_agreement,
    brier,
    calibration_slope,
    expected_calibration_error,
    soft_log_loss,
)
from ml.engine2_train.models import CANDIDATES, expand_soft, fit_soft, tune
from ml.engine2_train.select import choose


def sigmoid(z):
    return 1 / (1 + np.exp(-z))


def synthetic(n=600, seed=0, noise=0.05):
    """A world where risk rises with the first plan feature and falls with the first margin one."""
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, len(FEATURE_NAMES)))
    up = FEATURE_NAMES.index("instalment_to_income")
    down = FEATURE_NAMES.index("margin_monthly_p50_without")
    y = np.clip(sigmoid(1.8 * x[:, up] - 1.5 * x[:, down]) + rng.normal(0, noise, n), 0, 1)
    return Dataset(x, y, np.arange(n), FEATURE_NAMES)


# ---------------------------------------------------------------- soft labels and metrics
def test_duplicate_and_weight_gives_every_profile_both_classes_with_complementary_weights():
    x, y, w = expand_soft(np.array([[1.0], [2.0]]), np.array([0.2, 0.9]))

    assert x.shape == (4, 1) and list(y) == [1, 1, 0, 0]
    assert list(w) == pytest.approx([0.2, 0.9, 0.8, 0.1])


def test_brier_is_the_mean_squared_difference_from_the_soft_label():
    assert brier(np.array([0.5, 0.5]), np.array([0.3, 0.9])) == pytest.approx((0.04 + 0.16) / 2)


def test_soft_log_loss_matches_a_hand_calculation():
    expected = -(0.7 * math.log(0.6) + 0.3 * math.log(0.4))

    assert soft_log_loss(np.array([0.6]), np.array([0.7])) == pytest.approx(expected)


def test_auc_separates_at_risk_labels_from_the_rest_and_is_nan_with_one_class():
    labels = np.array([0.05, 0.1, 0.5, 0.9])
    assert auc_at_threshold(np.array([0.1, 0.2, 0.6, 0.8]), labels) == 1.0
    assert math.isnan(auc_at_threshold(np.array([0.1, 0.2]), np.array([0.01, 0.02])))


def test_a_perfectly_calibrated_predictor_has_slope_one_and_no_calibration_error():
    p = np.random.default_rng(1).uniform(0.02, 0.98, 4000)

    assert calibration_slope(p, p) == pytest.approx(1.0, abs=0.02)
    assert expected_calibration_error(p, p) == pytest.approx(0.0, abs=1e-9)


def test_an_overconfident_predictor_has_a_slope_below_one():
    target = np.random.default_rng(2).uniform(0.05, 0.95, 4000)
    logit = np.log(target / (1 - target))
    overconfident = sigmoid(2.5 * logit)

    assert calibration_slope(overconfident, target) < 0.6


def test_all_metrics_reports_every_key():
    p = np.random.default_rng(3).uniform(0.01, 0.99, 200)

    assert set(all_metrics(p, p)) == {"brier", "log_loss", "auc_at_030", "calibration_slope", "ece"}


# ---------------------------------------------------------------- models
@pytest.mark.parametrize("name", ["lightgbm", "xgboost", "random_forest"])
def test_monotone_constraints_are_honoured_even_when_the_data_pull_the_other_way(name):
    rng = np.random.default_rng(4)
    n = 800
    x = rng.normal(size=(n, len(FEATURE_NAMES)))
    up = FEATURE_NAMES.index("instalment_to_income")
    # a relationship that is NOT monotone in the +1 feature: the constraint must still win
    y = np.clip(0.5 + 0.4 * np.sin(2.5 * x[:, up]), 0, 1)
    fitted = fit_soft(name, {"n_estimators": 100}, x, y, FEATURE_NAMES, seed=0)

    grid = np.zeros((60, len(FEATURE_NAMES)))
    grid[:, up] = np.linspace(-3, 3, 60)
    for feature, direction in MONOTONE_DIRECTIONS.items():
        probe = np.zeros((60, len(FEATURE_NAMES)))
        probe[:, FEATURE_NAMES.index(feature)] = np.linspace(-3, 3, 60)
        pred = fitted.predict(probe)
        if direction == 1:
            assert np.all(np.diff(pred) >= -1e-9), feature
        if direction == -1:
            assert np.all(np.diff(pred) <= 1e-9), feature


def test_the_candidates_are_the_fixed_four():
    assert CANDIDATES == ("logistic", "lightgbm", "xgboost", "random_forest")
    with pytest.raises(ValueError, match="D-05"):
        fit_soft("neural_net", {}, np.zeros((4, 16)), np.zeros(4), FEATURE_NAMES)


def test_a_fitted_model_predicts_probabilities():
    data = synthetic()
    for name in CANDIDATES:
        fitted = fit_soft(name, {}, data.x, data.y, FEATURE_NAMES)
        pred = fitted.predict(data.x)
        assert pred.shape == (len(data),) and pred.min() >= 0 and pred.max() <= 1, name


def test_tuning_is_seeded_and_uses_only_the_data_it_is_given():
    data = synthetic(300)

    a = tune("xgboost", data.x, data.y, FEATURE_NAMES, trials=3, seed=1, scorer=brier)
    b = tune("xgboost", data.x, data.y, FEATURE_NAMES, trials=3, seed=1, scorer=brier)

    assert a == b and {"n_estimators", "max_depth", "learning_rate"} <= set(a)


# ---------------------------------------------------------------- cross-validation
def test_every_profile_is_tested_exactly_once_per_repeat_and_never_on_both_sides():
    data = synthetic(300)
    seen = {}
    for repeat, _, train, test in folds(data, repeats=3, k=5, seed=0):
        assert set(train).isdisjoint(test)
        seen.setdefault(repeat, []).extend(test.tolist())

    assert all(sorted(tested) == list(range(300)) for tested in seen.values())


def test_folds_are_stratified_on_the_label_deciles_and_reproducible():
    data = synthetic(500)
    strata = data.strata()

    a = [t.tolist() for _, _, _, t in folds(data, 1, 5, 0)]
    b = [t.tolist() for _, _, _, t in folds(data, 1, 5, 0)]

    assert a == b
    for test in a:
        counts = np.bincount(strata[test], minlength=10)
        assert counts.min() >= 5  # every fold sees every risk decile


def test_a_model_given_the_label_as_a_feature_scores_far_better_so_the_harness_would_notice():
    data = synthetic(400)
    leaky = data.x.copy()
    leaky[:, FEATURE_NAMES.index("limit_known")] = data.y  # a direction-0 (unconstrained) column
    settings = {"n_estimators": 80, "max_depth": 8, "min_samples_leaf": 3}

    honest = cross_validate("random_forest", data, 1, 3, trials=0, fixed_params=settings)
    leaking = cross_validate(
        "random_forest",
        Dataset(leaky, data.y, data.index, FEATURE_NAMES),
        1,
        3,
        trials=0,
        fixed_params=settings,
    )

    assert leaking.mean("brier") < honest.mean("brier") / 2


def test_nested_cross_validation_runs_for_every_candidate_and_beats_a_constant():
    data = synthetic(360)
    baseline = brier(np.full(len(data), data.y.mean()), data.y)

    for name in CANDIDATES:
        result = cross_validate(name, data, repeats=2, k=3, trials=2)
        assert len(result.fold_metrics) == 6
        assert not np.isnan(result.oof).any()
        assert result.mean("brier") < baseline, name


def make_result(name, briers, train=800, test=200):
    r = CvResult(name, FEATURE_NAMES)
    r.fold_metrics = [{"brier": b} for b in briers]
    r.fold_sizes = [(train, test)] * len(briers)
    return r


def test_the_corrected_resampled_t_test_matches_the_formula():
    a = make_result("a", [0.10, 0.12, 0.11, 0.13, 0.09, 0.10])
    b = make_result("b", [0.15, 0.15, 0.14, 0.18, 0.13, 0.14])
    d = np.array(a.metric("brier")) - np.array(b.metric("brier"))
    expected_t = d.mean() / math.sqrt((1 / 6 + 200 / 800) * np.var(d, ddof=1))

    mean, t, p = nadeau_bengio(a, b)

    assert mean == pytest.approx(d.mean()) and t == pytest.approx(expected_t) and p < 0.05
    assert mean < 0  # A is the better (lower) one


def test_identical_models_are_not_significantly_different():
    a = make_result("a", [0.1, 0.12, 0.11, 0.13, 0.09])

    assert nadeau_bengio(a, make_result("b", [0.1, 0.12, 0.11, 0.13, 0.09]))[2] == 1.0


# ---------------------------------------------------------------- the winner rule and calibration
def noisy(name, mean, spread=0.001, folds_=25, seed=0):
    rng = np.random.default_rng(seed)
    return make_result(name, list(mean + rng.normal(0, spread, folds_)))


def test_the_lowest_brier_wins_when_a_simpler_model_is_clearly_worse():
    choice = choose(
        {"logistic": noisy("logistic", 0.080), "xgboost": noisy("xgboost", 0.040, seed=1)}
    )

    assert choice.winner == "xgboost" and choice.reason == "lowest mean Brier score"


def test_a_simpler_model_within_one_standard_error_and_not_significantly_worse_wins():
    # the means differ by far less than the fold-to-fold noise, so no test can separate them
    a = noisy("logistic", 0.0501, spread=0.01, seed=2)
    b = noisy("xgboost", 0.0500, spread=0.01, seed=3)

    choice = choose({"logistic": a, "xgboost": b})

    assert choice.best_by_brier in {"logistic", "xgboost"}
    assert choice.winner == "logistic" and "within one SE" in choice.reason


def test_a_simpler_model_that_is_close_but_significantly_worse_does_not_win():
    best = make_result("random_forest", [0.040] * 24 + [0.0401])
    near = make_result("logistic", [0.0405] * 24 + [0.0406])  # consistently a bit worse, tiny noise

    choice = choose({"logistic": near, "random_forest": best})

    assert choice.winner == "random_forest"


def test_calibration_picks_a_correction_for_a_miscalibrated_predictor():
    target = np.random.default_rng(5).uniform(0.02, 0.98, 3000)
    miscalibrated = target**3  # systematically too low

    kind, scores = choose_calibration(miscalibrated, target)

    assert kind in {"platt", "isotonic"} and scores[kind] < scores["none"]


def test_calibration_leaves_a_calibrated_predictor_alone_or_close_to_it():
    target = np.random.default_rng(6).uniform(0.02, 0.98, 3000)

    kind, scores = choose_calibration(target, target)

    assert scores["none"] <= min(scores.values()) + 1e-6 or kind == "none"
    assert fit_calibrator("none", target, target).apply(target) is target


def test_an_unknown_calibration_is_refused():
    with pytest.raises(ValueError, match="unknown calibration"):
        fit_calibrator("magic", np.array([0.5]), np.array([0.5]))


# ---------------------------------------------------------------- reading labels
def test_load_labels_skips_locked_profiles_and_ignores_the_answer_keys(tmp_path):
    path = tmp_path / "labels.jsonl"
    good = {name: float(i) for i, name in enumerate(FEATURE_NAMES)}
    lines = [
        {"index": 0, "locked": False, "label": 0.25, "features": good, "truth": {"persona": "x"}},
        {"index": 1, "locked": True, "truth": {"persona": "y"}},
        {"index": 2, "locked": False, "label": 0.75, "features": good, "truth": {"persona": "z"}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")

    data = load_labels(path)

    assert list(data.index) == [0, 2] and list(data.y) == [0.25, 0.75]
    assert data.x.shape == (2, 16) and data.names == FEATURE_NAMES


def test_load_labels_refuses_an_empty_file(tmp_path):
    path = tmp_path / "labels.jsonl"
    path.write_text(json.dumps({"index": 0, "locked": True}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="no labelled profiles"):
        load_labels(path)


def test_a_dataset_subset_keeps_labels_and_the_chosen_columns_in_order():
    data = synthetic(50)
    subset = data.subset(("limit_known", "num_instalments"))

    assert subset.names == ("limit_known", "num_instalments")
    assert np.array_equal(subset.x[:, 1], data.x[:, FEATURE_NAMES.index("num_instalments")])
    assert np.array_equal(subset.y, data.y)


# ---------------------------------------------------------------- the lockbox (audit H5/H6)
def test_the_lockbox_is_every_tenth_profile_and_the_development_set_is_the_rest():
    data = synthetic(200)

    development, lockbox = split_lockbox(data)

    assert set(lockbox.index) == {i for i in range(200) if i % LOCKBOX_EVERY == 0}
    assert set(development.index).isdisjoint(lockbox.index)
    assert len(development) + len(lockbox) == 200
    assert development.x.shape[1] == 16 and len(lockbox.y) == len(lockbox.x)


def test_taking_a_subset_of_rows_keeps_every_array_aligned():
    data = synthetic(40)
    data = Dataset(data.x, data.y, data.index, data.names, p_without=data.y / 2,
                   capped=np.zeros(40, dtype=bool))  # fmt: skip

    part = data.take(data.index % 4 == 0)

    assert len(part) == 10 and np.array_equal(part.p_without, part.y / 2)
    assert part.capped.shape == (10,)
    assert data.subset(("limit_known",)).p_without is data.p_without  # extras survive a subset


def test_strata_are_quantile_bins_and_their_number_is_stated_not_assumed():
    rng = np.random.default_rng(0)
    y = np.concatenate([np.zeros(500), np.ones(300), rng.uniform(0, 1, 200)])
    data = Dataset(np.zeros((1000, 16)), y, np.arange(1000), FEATURE_NAMES)

    assert 1 < data.n_strata <= 10  # ties at exactly 0 and 1 collapse some of the ten bins
    assert data.n_strata == len(np.unique(data.strata()))


def test_the_low_baseline_subgroup_is_where_the_plan_decides_the_band():
    base = synthetic(100)
    data = Dataset(base.x, base.y, base.index, base.names, p_without=np.linspace(0, 1, 100))

    mask = data.subgroups()[LOW_BASELINE]

    assert mask.sum() == int((data.p_without < 0.10).sum())
    assert synthetic(10).subgroups() == {}  # no baseline recorded, no subgroup


def test_cross_validation_scores_the_subgroup_in_every_fold():
    base = synthetic(300)
    data = Dataset(base.x, base.y, base.index, base.names, p_without=np.linspace(0, 1, 300))

    result = cross_validate("logistic", data, repeats=1, k=3, trials=0)

    assert f"brier@{LOW_BASELINE}" in result.fold_metrics[0]
    assert result.mean(f"brier@{LOW_BASELINE}") >= 0


def test_band_agreement_counts_the_share_in_the_same_pre_registered_band():
    pred = np.array([0.05, 0.2, 0.5, 0.5])
    target = np.array([0.08, 0.35, 0.6, 0.1])

    agreement, confusion = band_agreement(pred, target)

    assert agreement == pytest.approx(0.5)
    assert confusion.tolist() == [[1, 0, 0], [0, 0, 1], [0, 1, 1]]  # rows: label, columns: model


def test_unconstrained_models_are_free_to_break_monotonicity():
    rng = np.random.default_rng(4)
    n = 800
    x = rng.normal(size=(n, len(FEATURE_NAMES)))
    up = FEATURE_NAMES.index("instalment_to_income")
    y = np.clip(0.5 + 0.4 * np.sin(2.5 * x[:, up]), 0, 1)
    probe = np.zeros((60, len(FEATURE_NAMES)))
    probe[:, up] = np.linspace(-3, 3, 60)

    free = fit_soft("xgboost", {"n_estimators": 100}, x, y, FEATURE_NAMES, constrained=False)
    held = fit_soft("xgboost", {"n_estimators": 100}, x, y, FEATURE_NAMES)

    assert np.any(np.diff(free.predict(probe)) < -1e-3)
    assert np.all(np.diff(held.predict(probe)) >= -1e-9)


# ---------------------------------------------------------------- the stored calibrator
@pytest.mark.parametrize("kind", ["none", "platt", "isotonic"])
def test_a_fitted_calibrator_survives_a_round_trip_through_json(kind):
    rng = np.random.default_rng(7)
    target = rng.uniform(0.02, 0.98, 800)
    pred = np.clip(target**2 + rng.normal(0, 0.03, 800), 0.01, 0.99)
    fitted = fit_calibrator(kind, pred, target)

    restored = Calibrator.from_dict(json.loads(json.dumps(fitted.to_dict())))

    probe = np.linspace(0, 1, 101)
    assert np.allclose(restored.apply(probe), fitted.apply(probe), atol=1e-9)


# ---------------------------------------------------------------- the label baseline
def test_label_facts_separate_the_baseline_from_the_purchase():
    from ml.engine2_train.labelstats import baseline_facts

    y = np.array([0.0, 0.05, 0.5, 1.0])
    base = np.array([0.0, 0.0, 0.5, 1.0])
    data = Dataset(np.zeros((4, 16)), y, np.arange(4), FEATURE_NAMES, p_without=base)

    facts = baseline_facts(data, paths=1000)

    assert facts["share_label_exactly_0"] == 0.25 and facts["share_label_exactly_1"] == 0.25
    assert facts["share_p_without_exactly_1"] == 0.25
    assert facts["share_p_without_at_or_above_safe_edge"] == 0.5
    assert facts["share_purchase_moves_the_band"] == 0.0  # 0 -> 0.05 stays Safe
    assert facts["share_purchase_changes_label_by_under_001"] == 0.75
    assert facts["monte_carlo_noise_floor_brier"] == pytest.approx(
        0.05 * 0.95 / 4 / 1000 + 0.25 / 4 / 1000
    )
    assert (
        baseline_facts(Dataset(data.x, y, data.index, data.names), None)[
            "monte_carlo_noise_floor_brier"
        ]
        is None
    )
