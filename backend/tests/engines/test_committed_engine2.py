"""The risk model that ships in models/engine2/: it loads against this code and behaves."""

import json

import numpy as np
import pytest

from app.engines.risk.artefact import MODEL_ROOT, load_if_present
from app.engines.risk.features import FEATURE_NAMES, FEATURE_SCHEMA_HASH

pytestmark = pytest.mark.skipif(
    not (MODEL_ROOT / "v1" / "metadata.json").exists(), reason="no risk model exported yet"
)


@pytest.fixture(scope="module")
def predictor():
    loaded = load_if_present()
    assert loaded is not None
    return loaded


@pytest.fixture(scope="module")
def metadata():
    return json.loads((MODEL_ROOT / "v1" / "metadata.json").read_text(encoding="utf-8"))


def test_the_committed_model_loads_against_the_running_code(predictor):
    assert predictor.feature_schema_hash == FEATURE_SCHEMA_HASH
    assert predictor.family == "lightgbm"


def test_the_export_recorded_that_it_matches_the_trained_model(metadata):
    onnx = metadata["parity"]["onnx_vs_trained_model"]
    served = metadata["parity"]["served_vs_trained_calibrated"]
    for check in (onnx, served):
        assert check["rows"] >= 1000
        assert check["max_abs_diff"] < 1e-3
        assert check["rows_over_1e-6"] <= 0.005 * check["rows"]


def test_the_model_was_built_with_the_monotone_constraints_and_says_where_it_came_from(metadata):
    assert metadata["monotone_constraints"] is True
    assert metadata["training"]["labels_sha256"]
    assert (
        metadata["metrics"]["lockbox_calibrated"]["brier"]
        < metadata["metrics"]["lockbox_constant_brier"]
    )


def test_the_reference_student_is_a_typical_safe_one_so_reasons_mean_more_than_not_typical(
    predictor, metadata
):
    baseline = [metadata["baseline"][name] for name in FEATURE_NAMES]
    p = predictor.predict(baseline)
    assert 0.0 < p < 0.10, p  # a typical student who is not at risk
    assert metadata["baseline_profiles"] >= 1000
    stretched = list(baseline)
    stretched[FEATURE_NAMES.index("instalment_to_income")] = 5.0
    stretched[FEATURE_NAMES.index("dsr_with_purchase")] = 5.0
    assert predictor.predict(stretched) > p  # a much heavier burden is riskier


def test_explanations_add_up_and_blame_the_features_that_changed(predictor, metadata):
    baseline = [metadata["baseline"][name] for name in FEATURE_NAMES]
    vector = list(baseline)
    for name in ("instalment_to_income", "dsr_with_purchase"):
        vector[FEATURE_NAMES.index(name)] = 4.0

    parts = predictor.contributions(vector)

    assert sum(parts) == pytest.approx(
        predictor.predict(vector) - predictor.predict(baseline), abs=1e-9
    )
    changed = {FEATURE_NAMES.index(n) for n in ("instalment_to_income", "dsr_with_purchase")}
    assert all(parts[i] == 0.0 for i in range(len(parts)) if i not in changed)
    assert np.isfinite(parts).all()
