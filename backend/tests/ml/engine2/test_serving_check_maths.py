"""The serving check's own arithmetic, on hand-built rows (no model artefact needed)."""

from collections import Counter
from types import SimpleNamespace

import pytest

from ml.engine2_train.serving_check import SERVING_SEED, render, summarise


def row(**over):
    base = {
        "index": 0,
        "p": 0.05,
        "p_simulated": 0.05,
        "band": "Safe",
        "band_simulated": "Safe",
        "seconds": 0.2,
        "factors": 1,
        "suggestion_found": False,
        "needed_suggestion": False,
        "evaluated": 0,
        "p_without": 0.02,
        "suggested_simulated": None,
        "suggestion_basis": None,
    }
    return {**base, **over}


def test_gap_and_band_agreement_are_computed_from_the_rows():
    rows = [
        row(p=0.20, p_simulated=0.10, band="Caution", band_simulated="Caution"),
        row(p=0.05, p_simulated=0.15, band="Safe", band_simulated="Caution"),
    ]
    result = summarise(rows, 2, 0, Counter())
    assert result["gap"]["mean"] == pytest.approx(0.0)
    assert result["gap"]["mean_abs"] == pytest.approx(0.10)
    assert result["gap"]["max_abs"] == pytest.approx(0.10)
    assert result["band_agreement"] == 0.5


def test_shares_over_nothing_are_none_not_zero():
    result = summarise([row()], 1, 0, Counter())  # nobody needed a suggestion
    assert result["non_safe"] == 0
    assert result["non_safe_short_before_purchase"] is None
    assert result["suggestion_reaches_safe"] is None
    assert result["suggestion_safe_by_simulation"] is None
    assert result["mean_evaluations_when_not_safe"] is None


def test_suggestions_are_counted_and_checked_against_the_simulation():
    rows = [
        row(
            needed_suggestion=True, band="Caution", suggestion_found=True, evaluated=5,
            p_without=0.30, suggested_simulated=0.05, suggestion_basis="model",
        ),
        row(
            needed_suggestion=True, band="At Risk", suggestion_found=True, evaluated=7,
            p_without=0.02, suggested_simulated=0.20, suggestion_basis="simulation",
        ),
    ]  # fmt: skip
    result = summarise(rows, 2, 0, Counter())
    assert result["non_safe"] == 2
    assert result["non_safe_short_before_purchase"] == 0.5
    assert result["suggestion_reaches_safe"] == 1.0
    assert result["suggestion_safe_by_simulation"] == 0.5
    assert result["suggestion_basis"] == {"model": 1, "simulation": 1}
    assert result["mean_evaluations_when_not_safe"] == 6


def test_the_report_says_n_a_when_there_is_nothing_to_share():
    result = summarise([row()], 1, 0, Counter())
    text = render(result, SimpleNamespace(version="v1", feature_schema_hash="abc"))
    assert "n/a" in text and "Engine 2 serving check" in text
    assert str(SERVING_SEED) in text
