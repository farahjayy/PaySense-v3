"""GET /api/model-info: which models are serving, for the About-the-model page."""

import pytest

from app.api.deps import get_today
from app.engines.risk.artefact import MODEL_ROOT, load_if_present


def test_requires_login(api):
    assert api.get("/api/model-info").status_code == 401


def test_without_a_risk_model_it_says_so_and_still_names_the_forecast_model(api, amir):
    api.app.state.predictor = None
    out = api.get("/api/model-info", headers=amir).json()

    assert out["forecast"] == {"model": "lstm", "version": "v1"}
    assert out["risk"] == {
        "available": False,
        "version": None,
        "family": None,
        "development_profiles": None,
        "lockbox_brier": None,
        "constant_brier": None,
        "feature_schema_hash": None,
    }


@pytest.mark.skipif(
    not (MODEL_ROOT / "v1" / "metadata.json").exists(), reason="no risk model exported yet"
)
def test_with_the_shipped_risk_model_it_reports_what_it_was_trained_on_and_how_well(api, amir):
    api.app.dependency_overrides[get_today] = lambda: None
    api.app.state.predictor = load_if_present()
    out = api.get("/api/model-info", headers=amir).json()["risk"]

    assert out["available"] is True and out["family"] == "lightgbm" and out["version"] == "v1"
    assert out["development_profiles"] == 9000
    assert 0 < out["lockbox_brier"] < out["constant_brier"] < 1
    assert len(out["feature_schema_hash"]) == 16
