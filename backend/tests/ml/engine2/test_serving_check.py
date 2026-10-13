"""The serving check script: its shape on a handful of profiles with the real artefact."""

from collections import Counter

import pytest

from app.engines.risk.artefact import MODEL_ROOT, load_if_present
from ml.datagen.params import load_params
from ml.datagen.profile import generate_dated_profile
from ml.engine2_train.labels import prepare
from ml.engine2_train.serving_check import SERVING_SEED, render, request_for, run, summarise

pytestmark = pytest.mark.skipif(
    not (MODEL_ROOT / "v1" / "metadata.json").exists(), reason="no risk model exported yet"
)


def test_a_few_profiles_give_a_complete_report():
    predictor = load_if_present()
    result = run(predictor, profiles=4)

    assert result["assessed"] + result["locked"] + result["rejected_by_plan_rules"] == 4
    assert result["assessed"] >= 1
    assert 0 <= result["band_agreement"] <= 1
    assert result["seconds"]["p50"] > 0
    text = render(result, predictor)
    assert "Engine 2 serving check" in text and "Time for a full assessment" in text


def test_a_manual_provider_student_is_asked_for_the_checkouts_own_numbers():
    params = load_params()
    for index in range(60):
        known = prepare(generate_dated_profile(params, SERVING_SEED, index))
        request = request_for(known)
        if known["proposal"].provider == "other":
            assert request.total_price_sen is None
            assert request.total_payable_sen and request.first_payment_date
            return
    pytest.skip("no manual-provider student in the first 60 profiles")


def test_summarising_nothing_assessed_does_not_divide_by_zero():
    with pytest.raises(ValueError):
        summarise([], 0, 0, Counter())
