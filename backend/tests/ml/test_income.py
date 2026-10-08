from datetime import date
from statistics import median

import pytest

from app.domain.categorize import guess_category
from ml.datagen.income import generate_income
from ml.datagen.params import load_params
from ml.datagen.rng import profile_rng

PARAMS = load_params()
START, END = date(2025, 1, 1), date(2025, 12, 31)


def income(persona, index, seed=11):
    return generate_income(PARAMS, persona, START, END, profile_rng(seed, index, "income"))


def monthly_totals(events):
    totals = {}
    for e in events:
        key = (e.date.year, e.date.month)
        totals[key] = totals.get(key, 0) + e.amount_sen
    return totals


def is_ptptn(event):
    return "PTPTN" in event.description


def is_allowance(event):
    return event.category == "Allowance" and not is_ptptn(event)


def test_every_event_is_a_positive_whole_sen_income_inside_the_window():
    for persona in ("frequent_bnpl", "budget_conscious", "irregular_income"):
        for index in range(30):
            for e in income(persona, index).events:
                assert isinstance(e.amount_sen, int) and e.amount_sen > 0
                assert e.type == "income"
                assert START <= e.date <= END


def test_the_same_seed_gives_the_same_income():
    assert income("frequent_bnpl", 5).events == income("frequent_bnpl", 5).events


def test_a_budget_conscious_student_gets_a_constant_monthly_allowance():
    for index in range(20):
        allowance = [e for e in income("budget_conscious", index).events if is_allowance(e)]
        assert len(allowance) == 12
        assert len({e.amount_sen for e in allowance}) == 1  # fixed, not varying
        assert len({e.date.day for e in allowance if e.date.day < 28}) <= 1  # same day each month


def test_allowance_descriptions_are_recognised_as_allowance_by_the_importer():
    for index in range(10):
        for e in income("budget_conscious", index).events:
            if is_allowance(e):
                assert guess_category(e.description) == "Allowance", e.description


def test_the_allowance_level_is_centred_on_the_persona_parameter():
    levels = []
    for index in range(300):
        allowance = [e for e in income("budget_conscious", index).events if is_allowance(e)]
        levels.append(allowance[0].amount_sen)

    target = PARAMS["income.allowance_median_sen.budget_conscious"]
    assert abs(median(levels) - target) / target < 0.08


def test_allowance_is_declared_as_a_monthly_recurring_income_in_the_ground_truth():
    result = income("budget_conscious", 2)

    truths = [
        t
        for t in result.truth
        if t.cadence == "monthly" and ("llowance" in t.name or "Duit" in t.name)
    ]
    (truth,) = truths
    assert truth.kind == "income"
    allowance = [e for e in result.events if is_allowance(e)]
    assert truth.amount_sen == allowance[0].amount_sen


def test_ptptn_lump_sums_arrive_in_the_assumed_months_and_use_a_cited_amount():
    options = set(PARAMS["income.ptptn_annual_sen"])
    months = PARAMS["income.ptptn_months"]
    seen = 0
    for index in range(200):
        lumps = [e for e in income("budget_conscious", index).events if is_ptptn(e)]
        if not lumps:
            continue
        seen += 1
        assert sorted(e.date.month for e in lumps) == sorted(months)
        annual = sum(e.amount_sen for e in lumps)
        per_year = PARAMS["income.ptptn_disbursements_per_year"]
        assert any(0 <= o - annual < per_year for o in options)  # integer split loses < n sen
    assert seen > 60  # roughly the assumed 55% of students


def test_the_share_with_ptptn_follows_the_persona_parameter():
    def share(persona):
        return sum(any(is_ptptn(e) for e in income(persona, i).events) for i in range(400)) / 400

    for persona in ("budget_conscious", "irregular_income"):
        target = PARAMS[f"income.ptptn_probability.{persona}"]
        assert share(persona) == pytest.approx(target, abs=0.08)


def test_part_time_pay_is_monthly_and_recognised_as_a_salary():
    found = 0
    for index in range(60):
        pay = [e for e in income("frequent_bnpl", index).events if e.category == "Salary"]
        if pay:
            found += 1
            assert len(pay) == 12
            assert guess_category(pay[0].description) == "Salary"
    assert 15 < found < 45  # about half of the frequent-BNPL persona


def test_gig_income_is_irregular_and_has_dry_spells():
    spreads, dry_months = [], 0
    for index in range(120):
        gig = [e for e in income("irregular_income", index).events if e.category == "Gig"]
        totals = monthly_totals(gig)
        values = [totals.get((2025, m), 0) for m in range(1, 13)]
        mean = sum(values) / 12
        if mean:
            spreads.append((sum((v - mean) ** 2 for v in values) / 12) ** 0.5 / mean)
        dry_months += sum(v < 0.5 * mean for v in values)
    assert median(spreads) > 0.2  # monthly gig pay genuinely varies
    assert dry_months / (120 * 12) > 0.05  # and some months are clearly dry


def test_gig_jobs_per_week_follow_the_assumed_mean():
    jobs = 0
    for index in range(150):
        jobs += sum(1 for e in income("irregular_income", index).events if e.category == "Gig")
    dry = PARAMS["income.gig_dry_spell_probability_per_month"]
    multiplier = PARAMS["income.gig_dry_spell_job_multiplier"]
    expected = PARAMS["income.gig_jobs_per_week_mean"] * (1 - dry * (1 - multiplier))

    assert jobs / (150 * 52) == pytest.approx(expected, rel=0.12)


def test_only_the_irregular_persona_has_gig_income():
    for persona in ("frequent_bnpl", "budget_conscious"):
        assert not any(e.category == "Gig" for i in range(20) for e in income(persona, i).events)


def test_the_irregular_persona_mostly_has_no_allowance():
    def has_allowance(events):
        return any(e.category == "Allowance" and not is_ptptn(e) for e in events)

    share = sum(has_allowance(income("irregular_income", i).events) for i in range(300)) / 300

    target = PARAMS["income.allowance_probability.irregular_income"]
    assert share == pytest.approx(target, abs=0.08)


def test_a_window_shorter_than_a_month_still_works():
    result = generate_income(
        PARAMS,
        "budget_conscious",
        date(2025, 3, 10),
        date(2025, 3, 16),
        profile_rng(1, 0, "income"),
    )

    assert all(date(2025, 3, 10) <= e.date <= date(2025, 3, 16) for e in result.events)
