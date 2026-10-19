"""Real-data check of the served band rule (plan 2026-10-19-local-completion, section 3).

The rules are scored through `served_error_record`, the function serving and the labels use, on
identical windows and identical random draws, and the plan's "clearly worse" rule is a pure
function of the rows.
"""

from datetime import date

import numpy as np
import pytest

from app.engines.forecasting.bands import Bucket, load_band_rule
from app.engines.forecasting.models import MovingAverage
from ml.engine1_eval import real_band_check as rbc
from ml.engine1_eval.data import Series

MONDAY = date(2024, 1, 1)


def _series(weeks: int, kind: str = "spend", source: str = "berka", seed: int = 1) -> Series:
    rng = np.random.default_rng(seed)
    values = 100.0 + 10.0 * rng.standard_normal(weeks)
    return Series(f"{source}-{seed}-{kind}", kind, source, MONDAY, np.clip(values, 0, None))


def _flat_rule(factor: float, clip: str = "week"):
    from app.engines.forecasting.bands import BandRule

    return BandRule("test", (Bucket(0, factor, factor),), clip)


@pytest.mark.parametrize(
    ("weeks", "label"),
    [(17, "17-25"), (25, "17-25"), (26, "26-38"), (38, "26-38"), (39, "39-51"), (52, "52+")],
)
def test_history_buckets_follow_the_served_table(weeks: int, label: str) -> None:
    assert rbc.bucket_label(weeks) == label


def test_every_rule_is_scored_on_the_same_origins() -> None:
    rows = rbc.score_series(
        _series(60), MovingAverage(13), {"A": _flat_rule(1.5), "B": _flat_rule(2.0)}, seed=7
    )
    origins = {rule: [r.weeks for r in rows if r.rule == rule] for rule in ("A", "B")}
    assert origins["A"] == origins["B"] == list(range(17, 60 - 13 + 1, rbc.STRIDE))


def test_two_identical_rules_get_identical_scores() -> None:
    rows = rbc.score_series(
        _series(70), MovingAverage(13), {"A": _flat_rule(1.5), "B": _flat_rule(1.5)}, seed=7
    )
    a = [(r.inside, r.bias) for r in rows if r.rule == "A"]
    b = [(r.inside, r.bias) for r in rows if r.rule == "B"]
    assert a == b and a


def test_scores_are_reproducible_for_a_seed_and_differ_for_another() -> None:
    args = (_series(70), MovingAverage(13), {"A": _flat_rule(1.0)})
    assert rbc.score_series(*args, seed=3) == rbc.score_series(*args, seed=3)
    assert rbc.score_series(*args, seed=3) != rbc.score_series(*args, seed=4)


def test_a_series_too_short_for_one_origin_gives_no_rows() -> None:
    assert rbc.score_series(_series(29), MovingAverage(13), {"A": _flat_rule(1.5)}, seed=1) == []


def test_the_record_comes_from_served_error_record_with_the_rule_and_the_history_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, str, str]] = []
    real = rbc.served_error_record

    def spy(values, start, forecaster, kind, rule, *args, **kwargs):
        calls.append((len(values), kind, rule.version))
        return real(values, start, forecaster, kind, rule, *args, **kwargs)

    monkeypatch.setattr(rbc, "served_error_record", spy)
    rbc.score_series(_series(40), MovingAverage(13), {"A": _flat_rule(1.5)}, seed=1)
    assert [c[0] for c in calls] == [17, 21, 25]
    assert {c[1:] for c in calls} == {("spend", "test")}


def test_the_rules_under_test_are_the_old_one_factor_rule_the_v2_table_and_the_served_rule() -> (
    None
):
    rules = rbc.rules_under_test()
    assert list(rules) == ["R1", "R2", "R3"]
    assert rules["R1"].clip == "week" and rules["R1"].factor(30, "spend") == 1.5
    assert rules["R2"].clip == "week" and rules["R2"].population is None
    assert rules["R3"] is load_band_rule()
    assert rules["R3"].clip == "month" and rules["R3"].population is not None


def _rows(spec: dict[tuple[str, str], tuple[int, int]]) -> list[rbc.Row]:
    """spec[(rule, bucket)] = (inside, total) -> rows with those counts."""
    weeks = {"17-25": 20, "26-38": 30, "39-51": 45, "52+": 60}
    rows = []
    for (rule, bucket), (inside, total) in spec.items():
        for i in range(total):
            rows.append(rbc.Row("berka", "s1", "spend", weeks[bucket], rule, i < inside, 0.0))
    return rows


def test_coverage_is_pooled_over_the_weeks_range_asked_for() -> None:
    rows = _rows({("R3", "26-38"): (6, 10), ("R3", "52+"): (9, 10), ("R3", "17-25"): (0, 10)})
    assert rbc.coverage(rows, "R3", min_weeks=26, max_weeks=None) == pytest.approx(0.75)
    assert rbc.coverage(rows, "R3", min_weeks=17, max_weeks=25) == pytest.approx(0.0)
    assert rbc.coverage(rows, "R2", min_weeks=17, max_weeks=None) is None


def _decision(r3_short, r3_long, r2_short=(8, 10), r2_long=(8, 10)):
    rows = _rows(
        {
            ("R2", "17-25"): r2_short,
            ("R2", "26-38"): r2_long,
            ("R3", "17-25"): r3_short,
            ("R3", "26-38"): r3_long,
        }
    )
    return rbc.decide(rows)


def test_r3_is_not_clearly_worse_when_it_matches_or_beats_the_old_rule() -> None:
    decision = _decision((8, 10), (9, 10))
    assert not decision.clearly_worse
    assert decision.short_gap == pytest.approx(0.0) and decision.long_gap == pytest.approx(0.1)


def test_a_loss_of_exactly_five_points_is_not_clearly_worse() -> None:
    assert not _decision((75, 100), (75, 100), (80, 100), (80, 100)).clearly_worse


def test_more_than_five_points_lost_for_long_histories_is_clearly_worse() -> None:
    decision = _decision((8, 10), (74, 100), (8, 10), (80, 100))
    assert decision.clearly_worse and decision.long_worse and not decision.short_worse


def test_more_than_five_points_lost_for_short_histories_is_clearly_worse() -> None:
    decision = _decision((74, 100), (8, 10), (80, 100), (8, 10))
    assert decision.clearly_worse and decision.short_worse and not decision.long_worse


def test_a_missing_group_cannot_pass_or_fail_quietly() -> None:
    rows = _rows({("R2", "26-38"): (8, 10), ("R3", "26-38"): (8, 10)})
    with pytest.raises(ValueError, match="17-25"):
        rbc.decide(rows)


def test_the_summary_lists_every_dataset_kind_bucket_and_rule() -> None:
    rows = _rows({("R3", "26-38"): (6, 10), ("R2", "26-38"): (7, 10)})
    table = rbc.summary_rows(rows)
    assert {(t["source"], t["kind"], t["bucket"], t["rule"]) for t in table} == {
        ("berka", "spend", "26-38", "R3"),
        ("berka", "spend", "26-38", "R2"),
    }
    r3 = next(t for t in table if t["rule"] == "R3")
    assert (r3["n"], r3["coverage"]) == (10, pytest.approx(0.6))


def _report_rows() -> list[rbc.Row]:
    return _rows(
        {
            ("R1", "17-25"): (3, 10),
            ("R2", "17-25"): (4, 10),
            ("R3", "17-25"): (7, 10),
            ("R1", "26-38"): (5, 10),
            ("R2", "26-38"): (6, 10),
            ("R3", "26-38"): (5, 10),
        }
    )


def test_the_section_states_the_rule_the_gaps_and_a_clearly_worse_verdict() -> None:
    text = rbc.render_section(_report_rows())
    assert "R3 is clearly worse than R2 on real data: **yes**" in text
    assert "26 weeks or more: -0.10" in text and "17-25 weeks: +0.30" in text
    assert "berka" in text and "17-25" in text and "0.70" in text


def test_the_section_says_so_when_r3_is_not_clearly_worse() -> None:
    rows = [r for r in _report_rows() if not (r.rule == "R3" and r.weeks == 30)]
    rows += _rows({("R3", "26-38"): (6, 10)})
    assert "clearly worse than R2 on real data: **no**" in rbc.render_section(rows)


def test_the_section_is_empty_of_a_verdict_when_a_group_is_missing() -> None:
    text = rbc.render_section(_rows({("R3", "26-38"): (6, 10), ("R2", "26-38"): (6, 10)}))
    assert "cannot be applied" in text and "**yes**" not in text and "**no**" not in text


def test_the_serving_check_section_scores_the_served_rule_files_end_to_end() -> None:
    from ml.engine1_eval.serving_check import real_band_section

    text = real_band_section(
        [_series(70, "spend", "synthetic")],
        [_series(70, "spend", "berka", 2), _series(70, "income", "berka", 3)],
        MovingAverage(13),
        seed=5,
    )
    assert "clearly worse than R2 on real data" in text
    assert "synthetic" in text and "berka" in text


def test_a_regeneration_without_stored_results_keeps_the_previous_parity_line_labelled() -> None:
    from ml.engine1_eval.serving_check import carry_over_parity

    previous = (
        "## 1. The served network reproduces the evaluated scores\n\n"
        "{'checked': 560, 'max_abs_mase_difference': 5.2e-07}\n\nmore\n"
    )
    none_stored = {"checked": 0, "note": "no stored evaluation results on this machine"}
    kept = carry_over_parity(none_stored, previous)
    assert "{'checked': 560, 'max_abs_mase_difference': 5.2e-07}" in kept
    assert "carried over from the previous report" in kept
    fresh = {"checked": 12, "max_abs_mase_difference": 1e-07}
    assert carry_over_parity(fresh, previous) == str(fresh)
    assert carry_over_parity(none_stored, None) == str(none_stored)
    assert carry_over_parity(none_stored, "no parity line here") == str(none_stored)
