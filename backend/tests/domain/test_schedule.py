"""Schedule maths. The first block re-expresses every case of v1's tests/test_schedule.py in sen
(same inputs, same expectations) so the port demonstrably preserves behaviour; the rest covers the
v2 additions: the provider-limit split (D-28) and the manual "Other provider" schedule (D-24)."""

from datetime import date

import pytest

from app.domain.providers import PROVIDERS, ProviderConfig
from app.domain.schedule import (
    add_months,
    build_manual_schedule,
    build_schedule,
    default_first_payment_date,
    generate_schedule,
    is_paid_at_checkout,
    split_for_limit,
    split_sen,
    total_payable_sen,
)


def _sum(schedule):
    return sum(item.amount_sen for item in schedule)


def _amounts(schedule):
    return [item.amount_sen for item in schedule]


# ---------------------------------------------------------------- ported from v1 (RM -> sen)


def test_sum_equals_total_payable_899_x6_zero_interest():
    schedule = generate_schedule(89900, 0, 6, date(2026, 5, 5))
    assert _sum(schedule) == 89900
    assert len(schedule) == 6


def test_sum_equals_total_payable_429_x3_with_monthly_fee():
    # 5% per month x 3 months = 15% on top of the price
    schedule = generate_schedule(42900, 5, 3, date(2026, 6, 20))
    assert _sum(schedule) == total_payable_sen(42900, 5, 3) == 49335


def test_awkward_rounding_100_x3():
    schedule = generate_schedule(10000, 0, 3, date(2026, 1, 15))
    assert _sum(schedule) == 10000
    assert schedule[0].amount_sen == 3333
    assert schedule[2].amount_sen == 3334


def test_due_dates_monthly_from_first_payment():
    schedule = generate_schedule(30000, 0, 3, date(2026, 3, 10))
    assert [s.due_date for s in schedule] == [
        date(2026, 3, 10),
        date(2026, 4, 10),
        date(2026, 5, 10),
    ]


def test_month_end_edge_31_jan():
    schedule = generate_schedule(30000, 0, 3, date(2026, 1, 31))
    assert [s.due_date for s in schedule] == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
    ]


def test_add_months_leap_year():
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_zero_interest_sum_equals_price():
    schedule = generate_schedule(123456, 0, 12, date(2026, 7, 1))
    assert _sum(schedule) == 123456


def test_monthly_fee_six_instalments_at_1_5_percent():
    schedule = generate_schedule(14762, 1.5, 6, date(2026, 9, 1))
    assert total_payable_sen(14762, 1.5, 6) == 16091
    assert _amounts(schedule) == [2681, 2681, 2681, 2681, 2681, 2686]


def test_zero_fee_three_instalments_leftover_sen_in_last():
    schedule = generate_schedule(14762, 0, 3, date(2026, 9, 1))
    assert total_payable_sen(14762, 0, 3) == 14762
    assert _amounts(schedule) == [4920, 4920, 4922]


def test_monthly_fee_twelve_instalments_at_1_5_percent():
    schedule = generate_schedule(14762, 1.5, 12, date(2026, 9, 1))
    assert total_payable_sen(14762, 1.5, 12) == 17419
    assert _amounts(schedule) == [1451] * 11 + [1458]


@pytest.mark.parametrize(
    ("price", "rate", "count"), [(14762, 1.5, 6), (89999, 1.25, 7), (10, 1.5, 12), (500000, 0.5, 6)]
)
def test_instalments_always_sum_to_the_total_exactly(price, rate, count):
    schedule = generate_schedule(price, rate, count, date(2026, 9, 1))
    assert _sum(schedule) == total_payable_sen(price, rate, count)
    assert all(
        a <= schedule[-1].amount_sen for a in _amounts(schedule)
    )  # remainder never lands early


def test_total_rounds_half_up_to_the_nearest_sen():
    # 0.50 x (1 + 0.015 x 6) = 0.545 exactly half a sen -> rounds up to 0.55
    assert total_payable_sen(50, 1.5, 6) == 55


def test_tiktok_first_bill_is_next_month_same_day():
    assert default_first_payment_date("tiktok_paylater", date(2026, 9, 25)) == date(2026, 10, 25)


def test_atome_first_payment_is_the_purchase_date():
    assert default_first_payment_date("atome", date(2026, 9, 25)) == date(2026, 9, 25)


def test_unknown_provider_keeps_purchase_date_start():
    assert default_first_payment_date("other", date(2026, 9, 25)) == date(2026, 9, 25)
    assert default_first_payment_date("grab_paylater", date(2026, 9, 25)) == date(2026, 9, 25)


def test_next_month_start_clamps_at_month_end():
    assert default_first_payment_date("tiktok_paylater", date(2026, 1, 31)) == date(2026, 2, 28)


def test_spaylater_first_bill_is_next_month_same_day():
    assert default_first_payment_date("spaylater", date(2026, 9, 25)) == date(2026, 10, 25)


def test_spaylater_repeats_the_same_day_each_month():
    schedule = build_schedule("spaylater", 30000, 0, 3, date(2026, 9, 26))
    assert [s.due_date for s in schedule] == [
        date(2026, 10, 26),
        date(2026, 11, 26),
        date(2026, 12, 26),
    ]


def test_pay_later_schedules_never_start_on_the_purchase_date_and_nothing_is_prepaid():
    purchase = date(2026, 9, 25)
    for provider in ("spaylater", "tiktok_paylater"):
        schedule = build_schedule(provider, 60000, 0, 6, purchase)
        assert schedule[0].due_date > purchase
        assert not any(item.paid_at_checkout for item in schedule)
        assert _sum(schedule) == 60000


def test_atome_schedule_charges_the_first_payment_at_checkout():
    schedule = build_schedule("atome", 30000, 0, 3, date(2026, 9, 25))
    assert [s.due_date for s in schedule] == [
        date(2026, 9, 25),
        date(2026, 10, 25),
        date(2026, 11, 25),
    ]
    assert [s.paid_at_checkout for s in schedule] == [True, False, False]
    assert schedule[0].amount_sen == 10000  # one-third at checkout
    assert is_paid_at_checkout("atome", date(2026, 9, 25), date(2026, 9, 25))


def test_atome_six_month_plan_still_charges_the_first_payment_at_checkout():
    schedule = build_schedule("atome", 14762, 1.5, 6, date(2026, 9, 25))
    assert schedule[0].paid_at_checkout is True
    assert schedule[0].amount_sen == 2681


def test_explicit_first_payment_date_overrides_the_provider_default():
    schedule = build_schedule("spaylater", 30000, 0, 3, date(2026, 9, 25), date(2026, 10, 10))
    assert schedule[0].due_date == date(2026, 10, 10)


def test_atome_first_payment_moved_off_the_purchase_date_is_not_prepaid():
    schedule = build_schedule("atome", 30000, 0, 3, date(2026, 9, 25), date(2026, 10, 25))
    assert not any(item.paid_at_checkout for item in schedule)


def test_adding_a_provider_is_one_config_entry(monkeypatch):
    monkeypatch.setitem(
        PROVIDERS,
        "testpay",
        ProviderConfig(
            key="testpay",
            label="TestPay",
            rule_driven=True,
            checkout_instalments=1,
            start_rule="months_after_purchase",
            start_offset_months=2,
        ),
    )
    schedule = build_schedule("testpay", 30000, 0, 3, date(2026, 9, 25))
    assert schedule[0].due_date == date(2026, 11, 25)
    assert schedule[0].paid_at_checkout is False  # first due is not the purchase date


def test_a_provider_without_a_monthly_fee_ignores_the_entered_rate(monkeypatch):
    monkeypatch.setitem(
        PROVIDERS,
        "nofeepay",
        ProviderConfig(key="nofeepay", label="NoFee", rule_driven=True, monthly_fee_applies=False),
    )
    schedule = build_schedule("nofeepay", 30000, 1.5, 3, date(2026, 9, 25))
    assert _sum(schedule) == 30000


# ---------------------------------------------------------------- v2: guards and invariants


@pytest.mark.parametrize("count", [0, -1, 37])
def test_instalment_count_must_be_between_1_and_36(count):
    with pytest.raises(ValueError, match="instalments"):
        generate_schedule(10000, 0, count, date(2026, 1, 1))


def test_price_must_be_positive():
    with pytest.raises(ValueError, match="price"):
        generate_schedule(0, 0, 3, date(2026, 1, 1))


def test_split_sen_puts_leftover_sen_in_the_last_instalment():
    assert split_sen(10001, 3) == [3333, 3333, 3335]
    assert split_sen(5, 1) == [5]


@pytest.mark.parametrize("price", [1, 99, 10000, 89999, 123457])
@pytest.mark.parametrize("rate", [0, 0.5, 1.5, 2.25, 5])
@pytest.mark.parametrize("count", [1, 2, 3, 6, 7, 12, 24, 36])
def test_every_schedule_sums_to_its_total_with_the_remainder_last(price, rate, count):
    total = total_payable_sen(price, rate, count)
    if total < count:  # cannot give every instalment at least one sen
        return
    schedule = generate_schedule(price, rate, count, date(2026, 1, 31))
    assert _sum(schedule) == total
    assert min(_amounts(schedule)) >= 1
    assert schedule[-1].amount_sen == max(_amounts(schedule))


# ---------------------------------------------------------------- v2: provider limit split (D-28)


def test_the_authors_worked_example_limit_200_price_300():
    split = split_for_limit(30000, 20000, 0, 3)

    assert (split.financed_sen, split.upfront_sen) == (20000, 10000)
    assert split.limit_applied is True


def test_no_limit_means_everything_is_financed():
    split = split_for_limit(30000, None, 1.5, 6)

    assert (split.financed_sen, split.upfront_sen) == (30000, 0)
    assert split.limit_applied is False


def test_a_limit_above_the_price_changes_nothing():
    split = split_for_limit(30000, 100000, 0, 3)

    assert (split.financed_sen, split.upfront_sen) == (30000, 0)


def test_the_cap_applies_to_the_total_payable_including_the_fee():
    # 1.5%/month x 6 = +9%: the largest financed principal whose price-plus-fee fits RM200.
    split = split_for_limit(30000, 20000, 1.5, 6)

    assert split.financed_sen == 18349
    assert split.upfront_sen == 30000 - 18349
    assert total_payable_sen(18349, 1.5, 6) <= 20000 < total_payable_sen(18350, 1.5, 6)
    assert split.total_payable_sen == total_payable_sen(18349, 1.5, 6)


@pytest.mark.parametrize("limit", [0, 1, 99, 5000, 19999, 20000, 29999])
@pytest.mark.parametrize("rate", [0, 1.5, 5])
def test_the_split_is_always_the_largest_financed_amount_that_fits(limit, rate):
    split = split_for_limit(30000, limit, rate, 6)

    assert split.financed_sen + split.upfront_sen == 30000
    assert total_payable_sen(split.financed_sen, rate, 6) <= limit or split.financed_sen == 0
    if split.financed_sen < 30000:
        assert total_payable_sen(split.financed_sen + 1, rate, 6) > limit


def test_an_exhausted_limit_finances_nothing():
    split = split_for_limit(30000, 0, 0, 3)

    assert (split.financed_sen, split.upfront_sen) == (0, 30000)


def test_a_limit_already_overdrawn_counts_as_exhausted():
    split = split_for_limit(30000, -5000, 0, 3)

    assert split.financed_sen == 0


# ---- v2: manual "Other provider" (D-24)


def test_manual_schedule_from_a_typed_instalment_amount():
    schedule = build_manual_schedule(date(2026, 11, 5), 3, instalment_sen=3333)

    assert _amounts(schedule) == [3333, 3333, 3333]
    assert [s.due_date for s in schedule] == [
        date(2026, 11, 5),
        date(2026, 12, 5),
        date(2027, 1, 5),
    ]
    assert not any(s.paid_at_checkout for s in schedule)


def test_manual_schedule_splits_a_typed_total_exactly_with_leftover_last():
    schedule = build_manual_schedule(date(2026, 11, 5), 3, total_payable_sen=10001)

    assert _amounts(schedule) == [3333, 3333, 3335]
    assert _sum(schedule) == 10001


def test_manual_schedule_applies_no_fee_and_no_provider_rule():
    schedule = build_manual_schedule(date(2026, 9, 25), 6, total_payable_sen=60000)

    assert _sum(schedule) == 60000  # never inflated by a fee formula
    assert schedule[0].due_date == date(2026, 9, 25)  # exactly the date the user typed


def test_manual_schedule_needs_exactly_one_amount():
    with pytest.raises(ValueError, match="exactly one"):
        build_manual_schedule(date(2026, 1, 1), 3)
    with pytest.raises(ValueError, match="exactly one"):
        build_manual_schedule(date(2026, 1, 1), 3, instalment_sen=100, total_payable_sen=300)


@pytest.mark.parametrize(
    ("count", "instalment", "total"),
    [(0, 100, None), (37, 100, None), (3, 0, None), (3, -5, None), (3, None, 0), (3, None, 2)],
)
def test_manual_schedule_rejects_impossible_inputs(count, instalment, total):
    with pytest.raises(ValueError, match="instalment|amount|total"):
        build_manual_schedule(
            date(2026, 1, 1), count, instalment_sen=instalment, total_payable_sen=total
        )


# ------------------------------------------------ review fix: no drift past month ends
def test_pay_later_dates_do_not_drift_after_a_short_month():
    # Bought on the 31st: due on the last day of each month it fits, never stuck on the 28th.
    schedule = build_schedule("spaylater", 40000, 0, 4, date(2026, 1, 31))

    assert [s.due_date for s in schedule] == [
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
    ]


def test_atome_dates_keep_the_purchase_day_of_month():
    schedule = build_schedule("atome", 30000, 0, 3, date(2026, 1, 30))

    assert [s.due_date for s in schedule] == [
        date(2026, 1, 30),
        date(2026, 2, 28),
        date(2026, 3, 30),
    ]


def test_a_user_typed_first_date_becomes_the_anchor_day():
    schedule = build_schedule("spaylater", 30000, 0, 3, date(2026, 1, 5), date(2026, 1, 31))

    assert [s.due_date for s in schedule] == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
    ]
