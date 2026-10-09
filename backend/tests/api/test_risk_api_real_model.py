"""The risk routes with the real shipped model and the real forecast network (no stubs)."""

import pytest

from app.api.deps import get_today
from app.api.forecast import get_forecaster
from app.engines.forecasting.serving import served_forecaster
from app.engines.risk.artefact import MODEL_ROOT, load_if_present
from tests.api.test_risk_api import TODAY, body, fill

pytestmark = pytest.mark.skipif(
    not (MODEL_ROOT / "v1" / "metadata.json").exists(), reason="no risk model exported yet"
)


@pytest.fixture(autouse=True)
def real(api):
    api.app.dependency_overrides[get_today] = lambda: TODAY
    api.app.dependency_overrides[get_forecaster] = served_forecaster
    api.app.state.predictor = load_if_present()
    yield
    api.app.dependency_overrides.clear()


def test_a_small_purchase_on_a_comfortable_income_is_safe_end_to_end(api, amir, fake_db):
    fill(fake_db, "amir", income=200000)
    res = api.post("/api/risk/check", json=body(total_price_sen=60000), headers=amir)

    assert res.status_code == 200
    out = res.json()
    assert out["status"] == "ok" and out["band"] == "Safe", out["probability"]
    assert out["versions"]["model"] == "v1"
    assert out["suggestion"]["status"] == "already_safe"
    assert all(0 <= f["contribution"] <= 1 for f in out["factors"])
    assert len(out["with_plan_curve"]["months"]) >= 3


def test_a_heavy_purchase_on_a_thin_income_is_not_safe_and_comes_with_reasons(api, amir, fake_db):
    fill(fake_db, "amir", income=50000, weekly=6000)
    out = api.post(
        "/api/risk/check", json=body(total_price_sen=300000, num_installments=2), headers=amir
    ).json()

    assert out["band"] == "At Risk"
    assert out["factors"], "an At Risk result should have at least one reason"
    assert out["suggestion"]["status"] in ("found", "none_found")


def test_confirming_with_the_real_model_freezes_the_same_numbers(api, amir, fake_db):
    fill(fake_db, "amir", income=200000)
    confirmed = api.post("/api/risk/confirm", json=body(total_price_sen=60000), headers=amir)

    assert confirmed.status_code == 201
    saved = api.get(f"/api/risk/checks/{confirmed.json()['check_id']}", headers=amir).json()
    assert saved["probability"] == pytest.approx(confirmed.json()["check"]["probability"], abs=1e-6)
    assert saved["band"] == "Safe"
