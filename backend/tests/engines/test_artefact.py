"""The served risk model artefact and the guards that stop a mismatched one from serving (D-09)."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from skl2onnx import to_onnx
from sklearn.linear_model import LogisticRegression

from app.engines.forecasting.onnx_model import MODEL_DIR as ENGINE1_DIR
from app.engines.forecasting.service import DASHBOARD_MONTHS, ERROR_INFLATION
from app.engines.forecasting.serving import ARTEFACT_VERSION
from app.engines.forecasting.simulate import BOOTSTRAP_BLOCK, RISK_CHECK_MAX_WEEKS
from app.engines.risk.artefact import ArtefactError, load_engine2, load_if_present
from app.engines.risk.features import FEATURE_NAMES, FEATURE_SCHEMA_HASH
from app.main import create_app

N = len(FEATURE_NAMES)
RNG = np.random.default_rng(7)
X = RNG.normal(size=(400, N)).astype(np.float32)
Y = (X[:, 0] + 0.5 * X[:, 3] - X[:, 5] > 0).astype(int)
LOGISTIC = LogisticRegression(max_iter=500).fit(X, Y)
USED = (0, 3, 5)  # the toy model really depends on these three features only
LOGISTIC.coef_[0, [i for i in range(N) if i not in USED]] = 0.0
PLATT = {"kind": "platt", "coef": 0.9, "intercept": 0.05}


def engine1_hashes() -> dict[str, str]:
    folder = ENGINE1_DIR / ARTEFACT_VERSION
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.glob("*.onnx"))
    }


def metadata(onnx_bytes: bytes, **overrides) -> dict:
    meta = {
        "version": "v1",
        "family": "logistic",
        "feature_names": list(FEATURE_NAMES),
        "feature_schema_hash": FEATURE_SCHEMA_HASH,
        "onnx_sha256": hashlib.sha256(onnx_bytes).hexdigest(),
        "calibrator": PLATT,
        "logit_eps": 1e-6,
        "baseline": {name: 0.0 for name in FEATURE_NAMES},
        "label": {
            "horizon_max_weeks": RISK_CHECK_MAX_WEEKS,
            "served_model_files": engine1_hashes(),
        },
        "serving_constants": {
            "RISK_CHECK_MAX_WEEKS": RISK_CHECK_MAX_WEEKS,
            "DASHBOARD_MONTHS": DASHBOARD_MONTHS,
            "ERROR_INFLATION": ERROR_INFLATION,
            "BOOTSTRAP_BLOCK": BOOTSTRAP_BLOCK,
        },
    }
    meta.update(overrides)
    return meta


def write(folder: Path, **overrides) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    onnx = to_onnx(LOGISTIC, X[:1], options={"zipmap": False}).SerializeToString()
    (folder / "model.onnx").write_bytes(onnx)
    (folder / "metadata.json").write_text(json.dumps(metadata(onnx, **overrides)), encoding="utf-8")
    return folder


def reference(vector) -> float:
    raw = float(LOGISTIC.predict_proba(np.asarray([vector], dtype=np.float32))[0, 1])
    clipped = min(max(raw, 1e-6), 1 - 1e-6)
    z = PLATT["coef"] * np.log(clipped / (1 - clipped)) + PLATT["intercept"]
    return float(1 / (1 + np.exp(-z)))


def test_a_consistent_artefact_loads_and_predicts_what_the_model_and_calibrator_say(tmp_path):
    predictor = load_engine2(write(tmp_path / "v1"))

    assert predictor.version == "v1"
    assert predictor.feature_schema_hash == FEATURE_SCHEMA_HASH
    for row in X[:25]:
        assert predictor.predict(row.tolist()) == pytest.approx(reference(row), abs=1e-6)


def test_isotonic_and_no_calibration_are_supported(tmp_path):
    raw = float(LOGISTIC.predict_proba(X[:1])[0, 1])
    none = load_engine2(write(tmp_path / "a", calibrator={"kind": "none"}))
    assert none.predict(X[0].tolist()) == pytest.approx(raw, abs=1e-6)

    iso = {"kind": "isotonic", "x": [0.0, 0.5, 1.0], "y": [0.0, 0.2, 1.0]}
    iso_predictor = load_engine2(write(tmp_path / "b", calibrator=iso))
    assert iso_predictor.predict(X[0].tolist()) == pytest.approx(
        np.interp(raw, iso["x"], iso["y"]), abs=1e-6
    )


def test_contributions_explain_the_gap_from_the_baseline_student_on_the_shown_scale(tmp_path):
    predictor = load_engine2(write(tmp_path / "v1"))
    vector = X[3].tolist()
    parts = predictor.contributions(vector)

    assert len(parts) == N
    baseline = predictor.predict([0.0] * N)
    assert sum(parts) == pytest.approx(predictor.predict(vector) - baseline, abs=1e-6)
    # features the model ignores contribute nothing; the ones it uses do
    assert all(abs(parts[i]) < 1e-6 for i in range(N) if i not in USED)
    assert any(abs(parts[i]) > 1e-3 for i in USED)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"feature_schema_hash": "0000000000000000"}, "feature schema"),
        ({"feature_names": list(reversed(FEATURE_NAMES))}, "feature order"),
        ({"feature_names": list(FEATURE_NAMES[:-1])}, "feature order"),
        (
            {
                "serving_constants": {
                    "RISK_CHECK_MAX_WEEKS": 52,
                    "DASHBOARD_MONTHS": DASHBOARD_MONTHS,
                    "ERROR_INFLATION": ERROR_INFLATION,
                    "BOOTSTRAP_BLOCK": BOOTSTRAP_BLOCK,
                }
            },
            "RISK_CHECK_MAX_WEEKS",
        ),
        ({"label": {"horizon_max_weeks": 52, "served_model_files": {}}}, "horizon"),
        (
            {
                "label": {
                    "horizon_max_weeks": RISK_CHECK_MAX_WEEKS,
                    "served_model_files": {"lstm_spend.onnx": "deadbeef"},
                }
            },
            "forecast model",
        ),
    ],
)
def test_an_artefact_that_disagrees_with_the_running_code_is_refused(tmp_path, overrides, message):
    with pytest.raises(ArtefactError, match=message):
        load_engine2(write(tmp_path / "v1", **overrides))


def test_a_model_file_that_was_changed_after_export_is_refused(tmp_path):
    folder = write(tmp_path / "v1")
    (folder / "model.onnx").write_bytes((folder / "model.onnx").read_bytes() + b"\0")
    with pytest.raises(ArtefactError, match="model file"):
        load_engine2(folder)


def test_missing_or_unreadable_files_are_refused_with_a_reason(tmp_path):
    with pytest.raises(ArtefactError, match="metadata"):
        load_engine2(tmp_path / "nothing")
    folder = write(tmp_path / "v1")
    (folder / "metadata.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ArtefactError, match="metadata"):
        load_engine2(folder)


def test_no_artefact_folder_means_no_predictor_but_a_broken_one_stops_start_up(tmp_path):
    assert load_if_present(tmp_path / "engine2") is None
    (tmp_path / "engine2").mkdir()
    assert load_if_present(tmp_path / "engine2") is None  # empty folder: nothing deployed

    write(tmp_path / "engine2" / "v1", feature_schema_hash="bad")
    with pytest.raises(ArtefactError):
        load_if_present(tmp_path / "engine2")


def test_the_newest_version_folder_is_the_one_served(tmp_path):
    write(tmp_path / "engine2" / "v1")
    write(tmp_path / "engine2" / "v2", version="v2")
    assert load_if_present(tmp_path / "engine2").version == "v2"


def test_the_app_factory_carries_the_predictor_it_is_given(settings, tmp_path):
    predictor = load_engine2(write(tmp_path / "v1"))
    assert create_app(settings, predictor=predictor).state.predictor is predictor
    assert create_app(settings).state.predictor is None
