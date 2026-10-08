from datetime import date
from math import exp, log
from statistics import median

import pytest

from ml.datagen.bnpl import BnplResult, generate_bnpl
from ml.datagen.params import load_params
from ml.datagen.purchase import MIN_INCOME_FLOOR_SEN, sample_purchase
from ml.datagen.rng import profile_rng

PARAMS = load_params()
AS_OF = date(2025, 12, 28)
START = date(2025, 1, 1)


def purchase(index, income=200_000, bnpl=None, seed=31):
    return sample_purchase(
        PARAMS, income, AS_OF, bnpl or BnplResult(), profile_rng(seed, index, "purchase")
    )


def test_the_same_seed_gives_the_same_purchase():
    assert purchase(4) == purchase(4)


def test_the_price_to_income_ratio_covers_the_intended_range_log_uniformly():
    low, high = PARAMS["purchase.price_to_monthly_income_range"]
    ratios = [purchase(i).price_sen / 200_000 for i in range(1500)]

    assert min(ratios) < low * 1.5 and max(ratios) > high * 0.6
    # log-uniform: the median ratio is the geometric centre of the range
    assert median(ratios) == pytest.approx(exp((log(low) + log(high)) / 2), rel=0.2)
    assert sum(r < 0.2 for r in ratios) > 100 and sum(r > 1.0 for r in ratios) > 100


def test_each_draw_is_a_valid_plan_proposal_for_the_chosen_provider():
    for i in range(300):
        p = purchase(i).proposal
        assert p.financed_sen + p.upfront_sen == p.total_price_sen
        assert p.num_installments == len(p.instalments)
        options = PARAMS[f"bnpl.instalment_options.{p.provider}"]
        assert p.num_installments in options


def test_the_purchase_is_dated_as_of_today():
    assert purchase(2).proposal.purchase_date == AS_OF


def test_a_modest_limit_produces_limit_capped_purchases():
    capped = 0
    for i in range(400):
        bnpl = generate_bnpl(PARAMS, "frequent_bnpl", START, AS_OF, profile_rng(7, i, "bnpl"))
        p = purchase(i, income=400_000, bnpl=bnpl).proposal
        capped += p.upfront_sen > 0
    assert capped > 10


def test_every_provider_appears_in_proportion_to_its_weight():
    counts = {}
    for i in range(1200):
        provider = purchase(i).proposal.provider
        counts[provider] = counts.get(provider, 0) + 1

    for provider in ("spaylater", "tiktok_paylater", "atome", "other"):
        target = PARAMS[f"bnpl.provider_weights.{provider}"]
        assert counts.get(provider, 0) / 1200 == pytest.approx(target, abs=0.06), provider


def test_an_income_of_nothing_uses_the_floor_instead_of_a_zero_price():
    p = purchase(0, income=0)

    assert (
        p.price_sen
        >= MIN_INCOME_FLOOR_SEN * PARAMS["purchase.price_to_monthly_income_range"][0] * 0.99
    )
    assert p.proposal.total_price_sen > 0
