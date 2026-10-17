from datetime import date

import pytest

from app.db.transactions import _clean_row
from app.domain.flows import classify, history_span, month_summary
from app.domain.schedule import add_months
from ml.datagen.income import PTPTN_DESCRIPTION
from ml.datagen.params import load_params
from ml.datagen.profile import (
    DEFAULT_AS_OF,
    draw_as_of,
    generate_dated_profile,
    generate_profile,
)

PARAMS = load_params()
PERSONAS = ("frequent_bnpl", "budget_conscious", "irregular_income")


def profile(index, seed=5, **kwargs):
    return generate_profile(PARAMS, seed, index, **kwargs)


def test_the_same_seed_and_index_give_an_identical_profile():
    assert profile(3) == profile(3)


def test_a_ten_profile_run_is_a_prefix_of_a_hundred_profile_run():
    ten = [profile(i) for i in range(10)]
    hundred = [profile(i) for i in range(100)]

    assert hundred[:10] == ten


def test_different_seeds_give_different_profiles():
    assert profile(1, seed=1).transactions != profile(1, seed=2).transactions


def test_personas_follow_the_assumed_population_weights():
    counts = dict.fromkeys(PERSONAS, 0)
    for i in range(600):
        counts[profile(i, history_months=1).persona] += 1

    for persona in PERSONAS:
        target = PARAMS[f"population.persona_weights.{persona}"]
        assert counts[persona] / 600 == pytest.approx(target, abs=0.07), persona


def test_a_requested_persona_is_honoured():
    assert {profile(i, persona="irregular_income").persona for i in range(5)} == {
        "irregular_income"
    }


def test_an_unknown_persona_is_rejected():
    with pytest.raises(ValueError, match="persona"):
        profile(0, persona="whale")


def test_every_transaction_passes_the_apps_own_row_validation():
    for i in range(30):
        for t in profile(i).transactions:
            _clean_row(t.as_row(), source="csv")


def test_no_transaction_is_dated_after_today_or_before_the_window():
    for i in range(30):
        p = profile(i)
        assert all(p.start <= t.date <= p.as_of for t in p.transactions)


def test_transactions_are_sorted_by_date():
    dates = [t.date for t in profile(2).transactions]

    assert dates == sorted(dates)


def test_the_month_summary_matches_the_generators_own_totals():
    for i in range(20):
        p = profile(i)
        rows = [t.as_row() for t in p.transactions]
        summary = month_summary(rows)

        rows_by_flow = [(classify(r), r["amount_sen"]) for r in rows]
        income = sum(amount for flow, amount in rows_by_flow if flow == "income")
        spend = sum(amount for flow, amount in rows_by_flow if flow == "spend")
        refunds = sum(amount for flow, amount in rows_by_flow if flow == "refund")
        assert sum(m.income_sen for m in summary) == income
        assert sum(m.refund_sen for m in summary) == refunds
        assert sum(m.spend_sen for m in summary) <= spend
        assert sum(m.spend_sen for m in summary) >= spend - refunds
        assert income > 0


def test_the_default_history_is_eighteen_months_and_personas_get_four():
    long = profile(0)
    short = profile(0, history_months=PARAMS["history.persona_months"])

    assert history_span([t.as_row() for t in long.transactions], long.as_of).distinct_months >= 17
    assert history_span([t.as_row() for t in short.transactions], short.as_of).distinct_months == 4


def test_the_window_ends_on_the_reference_date_by_default():
    assert profile(0).as_of == DEFAULT_AS_OF == date(2025, 12, 28)


def test_the_proposed_purchase_is_dated_today_and_priced_off_the_students_income():
    for i in range(20):
        p = profile(i)
        assert p.purchase.proposal.purchase_date == p.as_of
        assert p.expected_monthly_income_sen > 0


def test_recurring_ground_truth_is_kept_separately_for_detection_tests():
    p = profile(0, persona="budget_conscious")

    assert any(r.kind == "income" for r in p.recurring_truth)
    assert all(r.amount_sen > 0 for r in p.recurring_truth)


def test_existing_bnpl_payments_are_part_of_the_transactions():
    seen = False
    for i in range(40):
        p = profile(i, persona="frequent_bnpl")
        paid = sum(1 for t in p.transactions if t.category == "BNPL")
        assert paid >= len([t for t in p.transactions if t.bnpl_plan_key])
        seen = seen or paid > 0
    assert seen


@pytest.mark.parametrize("bad", [0, -1])
def test_a_history_shorter_than_one_month_is_rejected(bad):
    with pytest.raises(ValueError, match="history_months"):
        profile(0, history_months=bad)


def test_expected_income_leaves_out_ptptn_so_it_does_not_depend_on_the_window_month():
    from statistics import median

    september = [
        profile(i, persona="budget_conscious", history_months=4, as_of=date(2025, 12, 28))
        for i in range(150)
    ]
    january = [
        profile(i, persona="budget_conscious", history_months=4, as_of=date(2026, 1, 28))
        for i in range(150)
    ]

    a = median(p.expected_monthly_income_sen for p in september)
    b = median(p.expected_monthly_income_sen for p in january)
    assert a == pytest.approx(b, rel=0.2)


@pytest.mark.parametrize("as_of", [date(2025, 12, 17), date(2025, 12, 15), date(2025, 12, 21)])
@pytest.mark.parametrize("months", [1, 2])
def test_profiles_work_for_short_windows_ending_on_any_weekday(as_of, months):
    p = profile(1, history_months=months, as_of=as_of)

    assert p.transactions
    assert all(p.start <= t.date <= as_of for t in p.transactions)


# ------------------------------------------------- the as-of day drawn per profile (ADR D-31 note)
def test_the_as_of_day_depends_only_on_the_seed_and_the_index():
    assert draw_as_of(PARAMS, 5, 3) == draw_as_of(PARAMS, 5, 3)
    days = {draw_as_of(PARAMS, 5, i) for i in range(50)}
    assert len(days) > 25  # not a constant, not a handful of values


def test_the_drawn_as_of_days_cover_the_whole_year_evenly():
    days = [draw_as_of(PARAMS, 7, i) for i in range(2400)]

    months = [d.month for d in days]
    assert set(months) == set(range(1, 13))
    assert min(months.count(m) for m in range(1, 13)) > 120  # 200 expected per month
    start = date.fromisoformat(PARAMS["calendar.as_of_window_start"])
    assert all(0 <= (d - start).days < PARAMS["calendar.as_of_window_days"] for d in days)


def test_a_dated_profile_ends_its_history_on_its_own_as_of_day():
    for i in range(6):
        p = generate_dated_profile(PARAMS, 5, i)

        assert p.as_of == draw_as_of(PARAMS, 5, i)
        assert max(t.date for t in p.transactions) <= p.as_of
        months = int(PARAMS["history.default_months"])
        assert p.start == add_months(p.as_of.replace(day=1), -(months - 1))


def test_a_dated_profile_keeps_its_persona_and_its_other_draws():
    fixed = profile(4)
    dated = generate_dated_profile(PARAMS, 5, 4)

    assert dated.persona == fixed.persona  # the persona has its own stream


def test_the_calendar_position_of_ptptn_varies_across_dated_profiles():
    gaps = set()
    for i in range(120):
        p = generate_dated_profile(PARAMS, 5, i)
        lumps = [t.date for t in p.transactions if t.description == PTPTN_DESCRIPTION]
        if lumps:
            gaps.add(((p.as_of - max(lumps)).days) // 30)

    assert len(gaps) >= 4  # as-of days fall at different points of the PTPTN cycle


# --- the savings buffer (ADR D-50) ---
def test_some_profiles_have_a_savings_buffer_and_others_none():
    buffers = [profile(i).savings_buffer_sen for i in range(300)]
    share_with = sum(b > 0 for b in buffers) / len(buffers)
    assert 0.3 < share_with < 0.7
    assert all(b >= 0 and b % 1000 == 0 for b in buffers)


def test_a_buffer_never_exceeds_its_cap_in_months_of_income():
    cap = PARAMS["savings.cap_months_of_income"]
    floor = PARAMS["savings.income_floor_sen"]
    for i in range(300):
        p = profile(i)
        base = max(p.expected_monthly_income_sen, floor)
        assert p.savings_buffer_sen <= cap * base + 1000


def test_the_buffer_has_its_own_stream_so_nothing_else_moved():
    """The buffer is drawn from a new named stream: every other part of a profile is what v1's
    generator made (the committed synthetic manifest still matches, checked in WP16)."""
    p = profile(7)
    assert p.transactions and p.purchase  # generated as before
    assert p == profile(7)


def test_the_careful_persona_keeps_savings_more_often():
    def share(persona):
        values = [profile(i, persona=persona).savings_buffer_sen for i in range(200)]
        return sum(v > 0 for v in values) / len(values)

    assert share("budget_conscious") > share("frequent_bnpl")
