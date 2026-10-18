"""Engine v3: every band rule is kept under models/engine1/rules/, and the served file is one of
them, with its population record beside it when it names one."""

from app.engines.forecasting.bands import BAND_FILE, load_band_rule, text_digest
from app.engines.forecasting.population import digest

RULES = BAND_FILE.parent / "rules"


def test_the_served_rule_is_a_copy_of_a_kept_rule():
    kept = {text_digest(p): p for p in RULES.glob("v*/band_inflation.json")}
    assert "v2" in {p.parent.name for p in kept.values()}
    assert text_digest(BAND_FILE) in kept


def test_a_served_population_record_is_the_one_kept_with_its_rule():
    rule = load_band_rule()
    if rule.population is None:
        assert rule.clip == "week"  # v2: no record, weekly floor
        return
    kept = next(
        p for p in RULES.glob("v*/band_inflation.json") if text_digest(p) == text_digest(BAND_FILE)
    )
    assert digest(kept.parent / rule.population.file) == rule.population.sha256
    assert digest(BAND_FILE.parent / rule.population.file) == rule.population.sha256
