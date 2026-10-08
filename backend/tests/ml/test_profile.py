from datetime import date

import pytest

from app.db.transactions import _clean_row
from app.domain.flows import classify, history_span, month_summary
from ml.datagen.params import load_params
from ml.datagen.profile import DEFAULT_AS_OF, generate_profile

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
