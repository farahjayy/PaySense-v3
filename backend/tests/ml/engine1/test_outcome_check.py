"""The outcome check: served P(shortfall) scored against what really happened (no LSTM here)."""

import math
from datetime import date, timedelta

import numpy as np
import pytest

from app.engines.forecasting.bands import load_band_rule, parse_rule
from app.engines.forecasting.models import MovingAverage
from app.engines.forecasting.series import WeeklySeries
from ml.engine1_eval.band_calibration import COHORT, DEV_PROFILES, EVAL_POOL, dev_profiles
from ml.engine1_eval.band_calibration import test_profiles as heldout_profiles
from ml.engine1_eval.band_fresh_check import fresh_profiles
from ml.engine1_eval.outcome_check import (
    BUCKET_RANGES,
    CUTS,
    EPS,
    HORIZON,
    OUTCOME_PROFILES,
    RULE_FILES,
    Case,
    auc,
    band_rows,
    brier,
    calibration_rows,
    cases_for_student,
    confident_misses,
    ece,
    history_lengths,
    log_loss,
    month_to_date_sen,
    outcome_gate,
    outcome_profiles,
    paired_bootstrap,
    realised_shortfall,
    render,
    served_p,
    share_exact,
    summary_rows,
)
from ml.engine2_train.data import LOCKBOX_EVERY

MONDAY = date(2025, 9, 29)  # month-ends inside the next 13 weeks: 30 Sep, 31 Oct, 30 Nov
END = MONDAY + timedelta(days=7 * HORIZON - 1)


def _history(weeks: int = 17, spend: float = 0.0, income: float = 0.0, until: date = MONDAY):
    start = until - timedelta(days=7 * weeks)
    return WeeklySeries(start, np.full(weeks, spend), np.full(weeks, income))


def _next(**weeks: float) -> np.ndarray:
    """A 13-week path, zero except the named weeks (`w0`, `w1`, ...)."""
    values = np.zeros(HORIZON)
    for name, amount in weeks.items():
        values[int(name[1:])] = amount
    return values


# --- which students -----------------------------------------------------------------------------


def test_outcome_students_are_development_students_no_other_check_used():
    ids = outcome_profiles()
    assert len(ids) == len(set(ids)) == OUTCOME_PROFILES
    assert ids == outcome_profiles()  # seeded
    assert all(EVAL_POOL <= i < COHORT for i in ids)
    assert not [i for i in ids if i % LOCKBOX_EVERY == 0]  # never Engine 2's lockbox
    assert not set(ids) & set(heldout_profiles())  # never the 60 Engine 1 test students
    assert not set(ids) & set(fresh_profiles())  # never the 300 fresh-check students
    assert not set(ids) & set(dev_profiles(DEV_PROFILES))  # never the band table's own students


def test_one_history_length_per_bucket_seeded_and_the_whole_history_for_the_last():
    lengths = history_lengths(4001, 13, available=65)
    assert lengths == history_lengths(4001, 13, available=65)
    assert len(lengths) == len(BUCKET_RANGES)
    for weeks, (low, high) in zip(lengths[:-1], BUCKET_RANGES[:-1], strict=True):
        assert low <= weeks <= high
    assert lengths[-1] == 65
    assert history_lengths(4001, 26, available=40)[-1] < 52  # no 52+ case without 52 weeks


# --- the month so far -----------------------------------------------------------------------------


def test_month_to_date_is_the_cut_months_share_of_the_weekly_totals_by_day():
    cut = date(2025, 6, 30)  # 1 June 2025 is a Sunday: one day of the week of 26 May is in June
    series = _history(17, spend=0.0, income=700.0, until=cut)
    assert month_to_date_sen(series, cut) == 100 + 4 * 700
    assert (
        month_to_date_sen(_history(17, income=700.0, until=date(2025, 9, 1)), date(2025, 9, 1)) == 0
    )


# --- the realised outcome: the served definition on the real weeks -------------------------------


def test_realised_short_when_spending_outruns_income():
    assert realised_shortfall(_history(), _next(w1=500.0), _next(), END, 0)
    assert not realised_shortfall(_history(), _next(w1=500.0), _next(w0=7_000.0), END, 0)


def test_a_dip_that_recovers_before_the_month_end_is_not_a_shortfall():
    spend, income = _next(w1=70_000.0), _next(w2=140_000.0)
    assert not realised_shortfall(_history(), spend, income, END, 0)
    assert realised_shortfall(_history(), spend, _next(), END, 0)


def test_a_week_that_straddles_two_months_is_split_by_days():
    # 27 Oct - 2 Nov: 5 days in October, 2 in November. 5,600 of income in week 0 covers the
    # October part of 7,000 (5,000) but not the whole (short at 30 November).
    assert realised_shortfall(_history(), _next(w4=7_000.0), _next(w0=5_600.0), END, 0)
    assert not realised_shortfall(_history(), _next(w4=7_000.0), _next(w0=7_100.0), END, 0)


def test_the_month_so_far_counts_toward_the_first_month_end():
    assert realised_shortfall(_history(), _next(), _next(), END, -100)
    assert not realised_shortfall(_history(), _next(), _next(), END, 0)


# --- the served P on cheap forecasters ------------------------------------------------------------


def test_served_p_is_certain_when_the_record_has_no_error():
    flat = MovingAverage(13)  # exact on a constant series, so every error path is zero
    p, fallback = served_p(_history(30, spend=1_000.0), flat, END, 0, seed=1)
    assert (p, fallback) == (1.0, False)
    assert served_p(_history(30, spend=1_000.0, income=5_000.0), flat, END, 0, seed=1)[0] == 0.0
    v2 = load_band_rule(RULE_FILES["lstm"])  # the R2 rule: a user's own record at every length
    assert served_p(_history(17, spend=1_000.0), flat, END, 0, seed=1, rule=v2)[1]  # fallback
    # the served rule (R3, D-61) uses the population record below 26 weeks instead: no fallback
    assert not served_p(_history(17, spend=1_000.0), flat, END, 0, seed=1)[1]


class _Spy:
    """Fails if a forecaster ever sees a held-back week (marked with a sentinel)."""

    name = "spy"

    def __init__(self, sentinel: float) -> None:
        self.sentinel, self.longest = sentinel, 0

    def forecast(self, history, horizon, start):
        assert not np.any(np.asarray(history) >= self.sentinel)
        self.longest = max(self.longest, len(history))
        return np.full(horizon, float(np.mean(history[-13:])))


@pytest.mark.parametrize("cut", CUTS)
def test_no_held_back_week_reaches_a_forecaster(cut):
    weeks, sentinel = 78, 1e9
    spend = np.full(weeks, 100.0)
    spend[weeks - cut :] = sentinel
    income = np.full(weeks, 150.0)
    spy = _Spy(sentinel)
    cases = cases_for_student(4001, spend, income, date(2024, 7, 1), {"spy": spy}, cuts=(cut,))
    assert len(cases) == len(BUCKET_RANGES)
    assert spy.longest == weeks - cut
    assert {c.weeks for c in cases} >= {weeks - cut}
    assert all(c.realised for c in cases)  # the held-back spending is huge
    assert all(c.cut == cut and 0.0 <= c.p["spy"] <= 1.0 for c in cases)
    assert len({c.months for c in cases}) == 1


# --- scores ---------------------------------------------------------------------------------------


def test_brier_and_log_loss():
    y = np.array([0, 1])
    assert brier(np.array([0.0, 1.0]), y) == 0.0
    assert brier(np.array([0.5, 0.5]), y) == 0.25
    assert log_loss(np.array([0.5, 0.5]), y) == pytest.approx(math.log(2))
    # a certain miss is finite, clipped at half a simulated path
    assert log_loss(np.array([0.0]), np.array([1])) == pytest.approx(-math.log(EPS))


def test_auc_ranks_and_ties():
    y = np.array([0, 0, 1, 1])
    assert auc(np.array([0.1, 0.2, 0.8, 0.9]), y) == 1.0
    assert auc(np.array([0.9, 0.8, 0.2, 0.1]), y) == 0.0
    assert auc(np.full(4, 0.3), y) == 0.5
    assert auc(np.array([0.1, 0.2]), np.array([0, 0])) is None


def test_calibration_rows_and_ece():
    p = np.array([0.0, 0.0, 0.05, 0.15, 0.95, 1.0])
    y = np.array([0, 1, 0, 0, 1, 1])
    rows = {r.label: r for r in calibration_rows(p, y)}
    assert rows["0 exactly"].cases == 2 and rows["0 exactly"].realised == 0.5
    assert rows["(0, 0.1)"].cases == 1 and rows["[0.1, 0.2)"].cases == 1
    assert rows["[0.9, 1)"].cases == 1 and rows["1 exactly"].cases == 1
    assert sum(r.cases for r in rows.values()) == len(p)
    # ten bins: [0, 0.1) holds 0, 0, 0.05 (1 short); [0.1, 0.2) 0.15 (none); [0.9, 1] both short
    expected = (3 * abs(0.05 / 3 - 1 / 3) + abs(0.15 - 0) + 2 * abs(0.975 - 1)) / 6
    assert ece(p, y) == pytest.approx(expected)


def test_band_rows_share_exact_and_confident_misses():
    p = np.array([0.0, 0.05, 0.2, 0.5, 1.0, 1.0])
    y = np.array([1, 0, 0, 1, 1, 0])
    assert band_rows(p, y) == {"Safe": (2, 1), "Caution": (1, 0), "At Risk": (3, 2)}
    assert share_exact(p) == (pytest.approx(1 / 6), pytest.approx(2 / 6))
    assert confident_misses(p, y) == 2


def test_paired_bootstrap_by_student():
    same = np.array([0.1, 0.2, 0.3, 0.4])
    groups = np.array([1, 1, 2, 2])
    assert paired_bootstrap(same, same, groups, draws=50, seed=0) == (0.0, 0.0, 0.0)
    point, low, high = paired_bootstrap(same + 0.1, same, groups, draws=50, seed=0)
    assert point == pytest.approx(0.1) and low == pytest.approx(0.1) and high == pytest.approx(0.1)


# --- the page -------------------------------------------------------------------------------------


def _cases() -> list[Case]:
    out = []
    months = {13: ("2025-09", "2025-10", "2025-11"), 26: ("2025-06", "2025-07", "2025-08")}
    cut_dates = {13: date(2025, 9, 29), 26: date(2025, 6, 30)}
    for cut in CUTS:
        for profile, realised, mtd in ((4001, True, -50), (4002, False, 10), (4003, False, -5)):
            for weeks, lstm in ((17, 0.0), (30, 0.2), (45, 0.6), (78 - cut, 1.0)):
                p = {"lstm": lstm if realised else lstm / 2, "ma13": 0.3}
                fallback = {"lstm": weeks == 17, "ma13": False}
                out.append(
                    Case(profile, cut, weeks, realised, p, fallback, months[cut], cut_dates[cut],
                         mtd, realised and profile == 4001)
                )  # fmt: skip
    return out


def test_the_page_has_every_method_every_bucket_and_says_it_is_generated():
    cases = _cases()
    page = render(cases, [4001, 4002, 4003])
    assert "do not edit by hand" in page
    for cut in CUTS:
        assert f"## Cut {cut} weeks before the end" in page
    for label in ("LSTM, R2", "MA13, R2 (benchmark)", "constant (benchmark)"):
        assert page.count(f"| {label} |") >= 2 * (1 + len(BUCKET_RANGES) + 2)
    for bucket in ("17-25", "26-38", "39-51", "52+"):
        assert f"| {bucket} |" in page
    assert "| negative |" in page and "| zero or positive |" in page
    assert "| 0 exactly |" in page and "| 1 exactly |" in page
    assert "2025-09, 2025-10, 2025-11" in page and "2025-09-29" in page
    assert "already below RM0 at the first month-end: 1.000" in page
    assert "nan" not in page


def test_summary_rows_cover_each_cut_slice_and_method():
    rows = summary_rows(_cases())
    assert len(rows) == len(CUTS) * (1 + len(BUCKET_RANGES) + 2) * 3
    constant = [r for r in rows if r["method"] == "constant"]
    assert all(r["brier_skill"] == 0.0 and r["auc"] in (0.5, None) for r in constant)
    lstm_all = next(r for r in rows if r["method"] == "lstm" and r["slice"] == "all")
    assert lstm_all["cases"] == 12 and lstm_all["students"] == 3
    assert lstm_all["share_p0"] == pytest.approx(3 / 12)
    negative = next(r for r in rows if r["method"] == "constant" and r["slice"] == "negative")
    assert negative["cases"] == 8 and negative["mean_p"] == pytest.approx(0.5)  # its own rate


# --- engine v3: the same check under band rule R3 (plan 2026-10-18-engine-v3 §4.4, criterion 4) ---

BUCKETS_ONE = [{"min_weeks": 17, "spend": 2.4, "income": 1.3}]
MONTHLY = parse_rule({"version": "3", "clip": "month", "buckets": BUCKETS_ONE})
WEEKLY = parse_rule({"version": "2", "buckets": BUCKETS_ONE})


class _Alternating:
    """A forecaster whose errors alternate a week under and a week over the forecast."""

    name = "alternating"

    def forecast(self, history, horizon, start):
        return np.full(horizon, 1_000.0)


def test_served_p_follows_the_rules_clip():
    history = WeeklySeries(
        MONDAY - timedelta(days=7 * 30), np.tile([0.0, 2_000.0], 15), np.full(30, 1_050.0)
    )
    weekly = served_p(history, _Alternating(), END, 0, seed=1, rule=WEEKLY)[0]
    monthly = served_p(history, _Alternating(), END, 0, seed=1, rule=MONTHLY)[0]
    assert monthly < weekly  # the weekly floor deleted the weeks under the forecast


def test_a_variant_is_a_forecaster_with_its_own_rule():
    spend = np.full(78, 100.0)
    income = np.full(78, 150.0)
    flat = MovingAverage(13)
    cases = cases_for_student(
        4001, spend, income, date(2024, 7, 1), {"lstm": flat, "lstm_r3": (flat, MONTHLY)},
        cuts=(13,),
    )  # fmt: skip
    assert all(set(c.p) == {"lstm", "lstm_r3"} for c in cases)


def test_the_gate_is_the_paired_interval_of_r3_minus_r2_for_each_cut():
    cases = []
    for c in _cases():
        p = {**c.p, "lstm_r3": c.p["lstm"]}
        cases.append(Case(c.profile, c.cut, c.weeks, c.realised, p, c.fallback, c.months,
                          c.cut_date, c.month_to_date, c.realised_first))  # fmt: skip
    gate = outcome_gate(cases)
    assert set(gate) == {str(cut) for cut in CUTS}
    assert all(v == [0.0, 0.0, 0.0] for v in gate.values())
    assert outcome_gate(_cases()) == {}  # no R3 variant: nothing to gate
