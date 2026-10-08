from datetime import date

import pytest

from app.db import plans as plans_repo
from app.db.users import create as create_user
from ml.datagen.bnpl import generate_bnpl
from ml.datagen.params import load_params
from ml.datagen.rng import profile_rng
from tests.fakes import FakeSupabase

PARAMS = load_params()
START, END = date(2025, 1, 1), date(2025, 12, 28)


def bnpl(persona, index, seed=21, start=START, end=END):
    return generate_bnpl(PARAMS, persona, start, end, profile_rng(seed, index, "bnpl"))


def test_the_share_of_students_with_any_plan_follows_the_persona_parameter():
    for persona in ("frequent_bnpl", "budget_conscious", "irregular_income"):
        owners = sum(bool(bnpl(persona, i).plans) for i in range(300)) / 300
        target = PARAMS[f"bnpl.ownership_probability.{persona}"]
        assert owners == pytest.approx(target, abs=0.1), persona


def test_the_same_seed_gives_the_same_plans():
    assert bnpl("frequent_bnpl", 3).payments == bnpl("frequent_bnpl", 3).payments


def test_every_generated_plan_is_one_the_app_itself_would_accept():
    db = FakeSupabase()
    user_id = create_user(db, username="gen", display_name="Gen")["id"]
    created = 0
    for index in range(80):
        for plan in bnpl("frequent_bnpl", index).plans:
            p = plan.proposal
            assert p.financed_sen + p.upfront_sen == p.total_price_sen
            assert sum(i.amount_sen for i in p.instalments) == p.total_payable_sen
            plans_repo.create_plan(
                db,
                user_id,
                {
                    "item_name": plan.item_name,
                    "provider": p.provider,
                    "provider_label": p.provider_label,
                    "schedule_source": p.schedule_source,
                    "total_price_sen": p.total_price_sen,
                    "financed_sen": p.financed_sen,
                    "upfront_sen": p.upfront_sen,
                    "monthly_fee_rate_pct": p.monthly_fee_rate_pct,
                    "num_installments": p.num_installments,
                    "purchase_date": p.purchase_date,
                    "first_payment_date": p.first_payment_date,
                },
                p.instalments,
            )
            created += 1
    assert created > 40


def test_provider_choice_follows_the_assumed_weights():
    counts = {}
    for index in range(400):
        for plan in bnpl("frequent_bnpl", index).plans:
            counts[plan.proposal.provider] = counts.get(plan.proposal.provider, 0) + 1
    total = sum(counts.values())

    for provider in ("spaylater", "tiktok_paylater", "atome", "other"):
        target = PARAMS[f"bnpl.provider_weights.{provider}"]
        assert counts.get(provider, 0) / total == pytest.approx(target, abs=0.06), provider


def test_instalment_counts_come_from_what_each_provider_offers():
    for index in range(200):
        for plan in bnpl("frequent_bnpl", index).plans:
            options = PARAMS[f"bnpl.instalment_options.{plan.proposal.provider}"]
            assert plan.proposal.num_installments in options


def test_short_plans_are_free_and_long_plans_carry_the_long_plan_fee():
    saw_free = saw_fee = False
    for index in range(200):
        for plan in bnpl("frequent_bnpl", index).plans:
            p = plan.proposal
            if p.provider == "other":
                continue
            free = PARAMS[f"bnpl.zero_fee_instalments.{p.provider}"]
            if p.num_installments in free:
                assert p.monthly_fee_rate_pct == 0
                saw_free = True
            else:
                assert p.monthly_fee_rate_pct == PARAMS["bnpl.long_plan_fee_rate_pct"]
                saw_fee = True
    assert saw_free and saw_fee


def test_a_known_limit_is_never_exceeded_by_what_is_financed():
    checked = 0
    for index in range(300):
        result = bnpl("frequent_bnpl", index)
        for plan in result.plans:
            limit = result.limits.get(plan.proposal.provider)
            if limit is None or not plan.proposal.limit_applied:
                continue
            assert plan.proposal.total_payable_sen <= limit
            checked += 1
    assert checked > 20


def test_limits_stay_within_the_documented_cap():
    for index in range(300):
        for provider, limit in bnpl("frequent_bnpl", index).limits.items():
            if limit is not None:
                assert 0 < limit <= PARAMS[f"bnpl.limit_cap_sen.{provider}"]


def test_the_other_provider_uses_the_manual_path_with_a_typed_name():
    seen = False
    for index in range(300):
        for plan in bnpl("frequent_bnpl", index).plans:
            p = plan.proposal
            if p.provider == "other":
                seen = True
                assert p.schedule_source == "manual" and p.upfront_sen == 0
                assert p.provider_label and p.provider_label != "Other provider"
    assert seen


def test_payments_fall_inside_the_history_window_and_are_linked_bnpl_expenses():
    for index in range(80):
        result = bnpl("frequent_bnpl", index)
        keys = {plan.key for plan in result.plans}
        for t in result.payments:
            assert START <= t.date <= END
            assert t.type == "expense" and t.category == "BNPL"
            assert t.bnpl_plan_key in keys


def test_payment_behaviour_follows_the_cited_repayment_shares():
    on_time = late = unpaid = 0
    for index in range(500):
        result = bnpl("frequent_bnpl", index)
        for plan in result.plans:
            for seq, instalment in enumerate(plan.proposal.instalments, start=1):
                if (
                    instalment.paid_at_checkout
                    or instalment.due_date > END
                    or instalment.due_date < START
                ):
                    continue
                paid_on = plan.paid_dates.get(seq)
                if paid_on is None:
                    unpaid += 1
                elif paid_on == instalment.due_date:
                    on_time += 1
                else:
                    late += 1
    total = on_time + late + unpaid
    shares = (on_time / total, late / total, unpaid / total)
    cited_on_time = PARAMS["repayment.on_time_share"]
    cited_late = PARAMS["repayment.late_but_paid_share"]

    assert total > 2000
    assert shares[0] == pytest.approx(cited_on_time, abs=0.03)
    assert shares[1] == pytest.approx(cited_late, abs=0.03)
    assert shares[2] < 0.03


def test_an_atome_plan_pays_its_first_instalment_at_checkout():
    found = 0
    for index in range(400):
        for plan in bnpl("frequent_bnpl", index).plans:
            p = plan.proposal
            if p.provider == "atome" and START <= p.purchase_date <= END:
                assert p.instalments[0].paid_at_checkout
                assert plan.paid_dates[1] == p.purchase_date
                found += 1
    assert found > 20


def test_no_payment_is_dated_after_today():
    for index in range(100):
        assert all(t.date <= END for t in bnpl("frequent_bnpl", index).payments)
