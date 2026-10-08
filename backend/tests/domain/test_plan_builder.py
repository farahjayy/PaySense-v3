from datetime import date

import pytest

from app.domain.plan_builder import ProposalError, propose_plan

PURCHASE = date(2026, 9, 25)


def rule(provider, price, count, **kw):
    return propose_plan(
        provider=provider,
        purchase_date=PURCHASE,
        num_instalments=count,
        total_price_sen=price,
        **kw,
    )


def amounts(proposal):
    return [i.amount_sen for i in proposal.instalments]


# ------------------------------------------------------------------ rule-driven providers
def test_spaylater_bills_a_month_later_and_finances_the_whole_price_without_a_limit():
    p = rule("spaylater", 30000, 3)

    assert (p.financed_sen, p.upfront_sen, p.total_price_sen) == (30000, 0, 30000)
    assert p.first_payment_date == date(2026, 10, 25)
    assert amounts(p) == [10000, 10000, 10000]
    assert p.schedule_source == "provider_rule"
    assert p.provider_label == "SPayLater"
    assert p.limit_applied is False and p.remaining_limit_sen is None
    assert p.cash_at_purchase_sen == 0


def test_atome_charges_the_first_instalment_at_checkout():
    p = rule("atome", 30000, 3)

    assert p.instalments[0].paid_at_checkout is True
    assert p.cash_at_purchase_sen == 10000


def test_the_fee_applies_to_the_financed_part_and_raises_the_total_payable():
    p = rule("spaylater", 14762, 6, monthly_fee_rate_pct=1.5)

    assert p.total_payable_sen == 16091
    assert p.monthly_fee_rate_pct == 1.5


def test_the_authors_worked_example_limit_200_price_300():
    # D-28: only RM200 of RM300 can be financed; RM100 is paid at checkout.
    p = rule("spaylater", 30000, 2, remaining_limit_sen=20000)

    assert (p.financed_sen, p.upfront_sen) == (20000, 10000)
    assert amounts(p) == [10000, 10000]
    assert p.total_price_sen == 30000
    assert p.limit_applied is True and p.remaining_limit_sen == 20000
    assert p.cash_at_purchase_sen == 10000


def test_atome_with_a_limit_pays_both_the_excess_and_the_first_instalment_at_checkout():
    p = rule("atome", 30000, 2, remaining_limit_sen=20000)

    assert p.upfront_sen == 10000
    assert p.cash_at_purchase_sen == 10000 + 10000


def test_a_fee_bearing_plan_is_capped_on_the_total_payable_including_the_fee():
    p = rule("spaylater", 30000, 6, monthly_fee_rate_pct=1.5, remaining_limit_sen=20000)

    assert p.financed_sen == 18349
    assert p.total_payable_sen <= 20000
    assert sum(amounts(p)) == p.total_payable_sen


def test_an_exhausted_limit_cannot_finance_anything():
    with pytest.raises(ProposalError) as err:
        rule("spaylater", 30000, 3, remaining_limit_sen=0)

    assert err.value.code == "limit_exhausted"


def test_an_explicit_first_payment_date_overrides_the_provider_rule():
    p = rule("spaylater", 30000, 3, first_payment_date=date(2026, 10, 10))

    assert p.first_payment_date == date(2026, 10, 10)


def test_a_price_too_small_to_split_is_a_coded_error():
    with pytest.raises(ProposalError) as err:
        rule("spaylater", 2, 3)

    assert err.value.code == "amount_too_small"


@pytest.mark.parametrize("count", [0, 37])
def test_instalment_count_is_bounded(count):
    with pytest.raises(ProposalError) as err:
        rule("spaylater", 30000, count)

    assert err.value.code == "invalid_instalments"


def test_a_rule_driven_provider_needs_a_price():
    with pytest.raises(ProposalError) as err:
        propose_plan(provider="atome", purchase_date=PURCHASE, num_instalments=3)

    assert err.value.code == "price_required"


# ------------------------------------------------------------------ the manual "Other provider"
def test_other_provider_uses_exactly_the_typed_date_and_instalment_amount():
    p = propose_plan(
        provider="other",
        purchase_date=PURCHASE,
        num_instalments=3,
        first_payment_date=date(2026, 11, 3),
        provider_label="Grab PayLater",
        instalment_sen=3333,
    )

    assert amounts(p) == [3333, 3333, 3333]
    assert p.first_payment_date == date(2026, 11, 3)
    assert p.schedule_source == "manual"
    assert p.provider_label == "Grab PayLater"
    assert (p.financed_sen, p.upfront_sen, p.total_price_sen) == (9999, 0, 9999)
    assert p.monthly_fee_rate_pct == 0


def test_other_provider_splits_a_typed_total_exactly():
    p = propose_plan(
        provider="other",
        purchase_date=PURCHASE,
        num_instalments=3,
        first_payment_date=PURCHASE,
        provider_label="Boost PayFlex",
        total_payable_sen=10001,
    )

    assert amounts(p) == [3333, 3333, 3335]
    assert p.total_payable_sen == 10001


def test_other_provider_ignores_any_limit():
    p = propose_plan(
        provider="other",
        purchase_date=PURCHASE,
        num_instalments=2,
        first_payment_date=PURCHASE,
        provider_label="X",
        total_payable_sen=30000,
        remaining_limit_sen=1000,
    )

    assert (p.financed_sen, p.upfront_sen) == (30000, 0)
    assert p.limit_applied is False


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"provider_label": "X", "instalment_sen": 100}, "first_payment_date_required"),
        ({"first_payment_date": PURCHASE, "instalment_sen": 100}, "provider_label_required"),
        ({"first_payment_date": PURCHASE, "provider_label": "X"}, "amount_required"),
        (
            {
                "first_payment_date": PURCHASE,
                "provider_label": "X",
                "instalment_sen": 100,
                "total_payable_sen": 300,
            },
            "amount_required",
        ),
        (
            {"first_payment_date": PURCHASE, "provider_label": "  ", "instalment_sen": 1},
            "provider_label_required",
        ),
        (
            {
                "first_payment_date": PURCHASE,
                "provider_label": "X",
                "instalment_sen": 100,
                "total_price_sen": 500,
            },
            "price_not_allowed",
        ),
    ],
)
def test_other_provider_input_errors_are_coded(kwargs, code):
    with pytest.raises(ProposalError) as err:
        propose_plan(provider="other", purchase_date=PURCHASE, num_instalments=3, **kwargs)

    assert err.value.code == code


def test_a_rule_driven_provider_refuses_manual_fields():
    with pytest.raises(ProposalError) as err:
        rule("spaylater", 30000, 3, instalment_sen=100)

    assert err.value.code == "manual_fields_not_allowed"


def test_an_unknown_provider_is_refused():
    with pytest.raises(ProposalError) as err:
        propose_plan(provider="grab_paylater", purchase_date=PURCHASE, num_instalments=3)

    assert err.value.code == "unknown_provider"
