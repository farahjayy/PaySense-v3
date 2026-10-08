from datetime import date

import pytest

from app.domain.categorize import guess_category
from ml.datagen.bills import PHONE_TEMPLATES, SUBSCRIPTION_TEMPLATES, generate_bills
from ml.datagen.params import load_params
from ml.datagen.rng import profile_rng

PARAMS = load_params()
START, END = date(2025, 1, 1), date(2025, 12, 31)


def bills(index, seed=5, start=START, end=END):
    return generate_bills(PARAMS, start, end, profile_rng(seed, index, "bills"))


def by_name(result, fragment):
    return [e for e in result.events if fragment.lower() in e.description.lower()]


def test_every_bill_is_a_positive_expense_with_a_category_the_importer_recognises():
    for index in range(40):
        for e in bills(index).events:
            assert isinstance(e.amount_sen, int) and e.amount_sen > 0
            assert e.type == "expense"
            assert START <= e.date <= END
            assert guess_category(e.description) == e.category, e.description


def test_the_same_seed_gives_the_same_bills():
    assert bills(3).events == bills(3).events


def test_rent_is_a_fixed_amount_on_the_same_day_every_month():
    seen = 0
    for index in range(80):
        rent = by_name(bills(index), "rent")
        if not rent:
            continue
        seen += 1
        assert len(rent) == 12
        assert len({e.amount_sen for e in rent}) == 1
        assert len({e.date.day for e in rent if e.date.day <= 28}) == 1
        low, high = PARAMS["bills.rent_monthly_sen_range"]
        assert low <= rent[0].amount_sen <= high
    assert seen / 80 == pytest.approx(PARAMS["bills.rent_probability"], abs=0.12)


def test_the_phone_bill_varies_by_no_more_than_the_stated_jitter():
    jitter = PARAMS["bills.variable_bill_jitter_ratio"]
    for index in range(40):
        result = bills(index)
        phone = [e for e in result.events if e.description in PHONE_TEMPLATES]
        assert len(phone) == 12
        (truth,) = [t for t in result.truth if t.name in PHONE_TEMPLATES]
        # the answer key holds the typical level, which every month stays within the jitter of
        assert all(
            abs(e.amount_sen - truth.amount_sen) <= truth.amount_sen * jitter + 1 for e in phone
        )


def test_subscriptions_follow_the_stated_probability_and_are_at_most_two():
    counts = []
    for index in range(200):
        names = {
            e.description for e in bills(index).events if e.description in SUBSCRIPTION_TEMPLATES
        }
        counts.append(len(names))
        assert len(names) <= 2
    share = sum(c > 0 for c in counts) / 200
    assert share == pytest.approx(PARAMS["bills.subscription_probability"], abs=0.1)


def test_a_month_end_day_is_clamped_in_short_months():
    for index in range(60):
        for e in bills(index).events:
            assert e.date.day <= 31 and e.date.month in range(1, 13)  # never an invalid date


def test_ground_truth_lists_each_monthly_bill_with_its_anchor():
    result = bills(0)
    assert result.truth, "expected at least one recurring bill for this seed"
    for truth in result.truth:
        assert truth.kind == "bill" and truth.cadence == "monthly"
        matching = [e for e in result.events if e.description == truth.name]
        assert matching and matching[0].date == truth.anchor_date


def test_a_window_without_a_full_month_only_contains_bills_that_fall_inside_it():
    result = bills(2, start=date(2025, 3, 6), end=date(2025, 3, 20))

    assert all(date(2025, 3, 6) <= e.date <= date(2025, 3, 20) for e in result.events)
