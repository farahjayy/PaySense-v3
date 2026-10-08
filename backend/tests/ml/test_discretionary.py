from datetime import date, timedelta
from statistics import mean, median

import pytest

from app.domain.categorize import guess_category
from ml.datagen.calendar import exam_weeks, iter_weeks, week_start
from ml.datagen.discretionary import generate_discretionary
from ml.datagen.params import load_params
from ml.datagen.rng import profile_rng

PARAMS = load_params()
START, END = date(2025, 1, 1), date(2025, 12, 28)  # 52 whole weeks (Wed 1 Jan -> Sun 28 Dec)


def spending(persona, index, *, income_dates=frozenset(), start=START, end=END, seed=3):
    return generate_discretionary(
        PARAMS, persona, start, end, income_dates, profile_rng(seed, index, "discretionary")
    )


def spend_only(txns):
    return [t for t in txns if t.type == "expense" and t.category not in ("Transfer",)]


def weekly_totals(txns, start=START, end=END):
    totals = {w: 0 for w in iter_weeks(start, end)}
    for t in spend_only(txns):
        totals[week_start(t.date)] += t.amount_sen
    return totals


def test_every_transaction_is_a_positive_whole_sen_inside_the_window():
    for persona in ("frequent_bnpl", "budget_conscious", "irregular_income"):
        for index in range(15):
            for t in spending(persona, index):
                assert isinstance(t.amount_sen, int) and t.amount_sen >= 100
                assert START <= t.date <= END
                assert t.type in ("expense", "income")


def test_the_same_seed_gives_the_same_spending():
    assert spending("frequent_bnpl", 4) == spending("frequent_bnpl", 4)


@pytest.mark.parametrize("persona", ["budget_conscious", "frequent_bnpl", "irregular_income"])
def test_the_typical_monthly_spend_is_centred_on_the_persona_parameter(persona):
    medians = []
    for index in range(120):
        monthly = {}
        for t in spend_only(spending(persona, index)):
            monthly[t.date.month] = monthly.get(t.date.month, 0) + t.amount_sen
        medians.append(median(monthly.values()))

    target = PARAMS[f"discretionary.monthly_median_sen.{persona}"]
    assert median(medians) == pytest.approx(target, rel=0.15)


def test_the_cited_budget_conscious_centre_sits_inside_the_cited_modal_band():
    target = PARAMS["discretionary.monthly_median_sen.budget_conscious"]

    assert 20100 <= target <= 40000  # RM201-400, Tok & Cheah (2024)


def test_week_to_week_spending_is_over_dispersed():
    cvs = []
    for index in range(80):
        values = list(weekly_totals(spending("budget_conscious", index)).values())
        cvs.append(
            (sum((v - mean(values)) ** 2 for v in values) / len(values)) ** 0.5 / mean(values)
        )
    assert 0.35 < median(cvs) < 0.9


def test_weekends_carry_more_spending_than_early_weekdays():
    by_weekday = [0] * 7
    for index in range(80):
        for t in spend_only(spending("budget_conscious", index)):
            by_weekday[t.date.weekday()] += t.amount_sen

    assert by_weekday[4] + by_weekday[5] > 1.25 * (by_weekday[0] + by_weekday[1])


def test_spending_rises_in_the_days_after_income_lands():
    paydays = {date(2025, m, 5) for m in range(1, 13)}
    after, other = [], []
    for index in range(60):
        daily = {}
        for t in spend_only(spending("budget_conscious", index, income_dates=frozenset(paydays))):
            daily[t.date] = daily.get(t.date, 0) + t.amount_sen
        day = START
        while day <= END:
            bucket = after if any(0 <= (day - p).days <= 2 for p in paydays) else other
            bucket.append(daily.get(day, 0))
            day += timedelta(days=1)

    assert mean(after) > 1.08 * mean(other)


def test_exam_weeks_are_quieter_than_other_weeks():
    exams = exam_weeks(
        START,
        END,
        exam_months=PARAMS["discretionary.exam_months"],
        per_semester=PARAMS["discretionary.exam_weeks_per_semester"],
    )
    quiet, normal = [], []
    for index in range(100):
        for week, total in weekly_totals(spending("budget_conscious", index)).items():
            (quiet if week in exams else normal).append(total)

    assert exams
    assert mean(quiet) < 0.9 * mean(normal)


def test_some_weeks_are_unusually_large():
    big = weeks = 0
    for index in range(100):
        values = list(weekly_totals(spending("budget_conscious", index)).values())
        typical = median(values)
        big += sum(v > 1.9 * typical for v in values)
        weeks += len(values)
    assert big / weeks > 0.02


def test_category_spend_shares_follow_the_cited_household_weights():
    spent = {}
    for index in range(80):
        for t in spend_only(spending("budget_conscious", index)):
            spent[t.category] = spent.get(t.category, 0) + t.amount_sen
    total = sum(spent.values())
    food, eat, transport = (
        PARAMS["discretionary.category_weight_food"],
        PARAMS["discretionary.category_weight_eating_out"],
        PARAMS["discretionary.category_weight_transport"],
    )
    other = PARAMS["discretionary.category_other_share"]
    scale = (1 - other) / (food + eat + transport)

    assert spent["Food"] / total == pytest.approx((food + eat) * scale, rel=0.12)
    assert spent["Transport"] / total == pytest.approx(transport * scale, rel=0.12)
    other_split = {
        n: PARAMS[f"discretionary.other_split_{n}"]
        for n in ("shopping", "entertainment", "education")
    }
    for name, weight in other_split.items():
        target = other * weight / sum(other_split.values())
        assert spent[name.title()] / total == pytest.approx(target, rel=0.2), name


def test_a_shopping_or_education_purchase_is_typically_bigger_than_a_bus_fare():
    sizes = {}
    for index in range(60):
        for t in spend_only(spending("budget_conscious", index)):
            sizes.setdefault(t.category, []).append(t.amount_sen)

    assert median(sizes["Shopping"]) > 2 * median(sizes["Transport"])
    assert median(sizes["Education"]) > median(sizes["Food"])


def test_the_importer_recovers_the_intended_category_at_the_documented_rate():
    agree = seen = 0
    for index in range(60):
        for t in spend_only(spending("budget_conscious", index)):
            seen += 1
            agree += guess_category(t.description) == t.category
    miss = PARAMS["discretionary.unrecognisable_description_share"]

    assert agree / seen == pytest.approx(1 - miss, abs=0.05)


def test_refunds_and_transfers_appear_at_the_assumed_monthly_rates():
    refunds = transfers = 0
    for index in range(100):
        txns = spending("budget_conscious", index)
        refunds += sum(t.category == "Refund" for t in txns)
        transfers += sum(t.category == "Transfer" for t in txns)
    months = 100 * 12

    assert refunds / months == pytest.approx(
        PARAMS["discretionary.refund_probability_per_month"], abs=0.04
    )
    assert transfers / months == pytest.approx(
        PARAMS["discretionary.transfer_probability_per_month"], abs=0.06
    )
    assert all(
        t.type == "income" for t in spending("budget_conscious", 1) if t.category == "Refund"
    )
    assert all(
        t.type == "expense" for t in spending("budget_conscious", 1) if t.category == "Transfer"
    )


def test_a_partial_first_and_last_week_only_spends_on_the_days_inside_the_window():
    start, end = date(2025, 3, 5), date(2025, 3, 11)  # Wed -> Tue: two partial weeks

    for index in range(20):
        assert all(
            start <= t.date <= end
            for t in spending("budget_conscious", index, start=start, end=end)
        )


def test_a_one_day_window_does_not_break():
    txns = spending("budget_conscious", 0, start=date(2025, 3, 5), end=date(2025, 3, 5))

    assert all(t.date == date(2025, 3, 5) for t in txns)
