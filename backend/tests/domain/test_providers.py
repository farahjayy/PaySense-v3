import re
from pathlib import Path

import pytest

from app.domain.providers import PROVIDER_KEYS, PROVIDERS, get_provider

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "0001_init.sql"


def test_exactly_the_four_providers_of_adr_d24_exist():
    assert PROVIDER_KEYS == ("spaylater", "tiktok_paylater", "atome", "other")
    assert tuple(PROVIDERS) == PROVIDER_KEYS


@pytest.mark.parametrize("key", ["spaylater", "tiktok_paylater"])
def test_pay_later_providers_charge_nothing_at_checkout_and_bill_a_month_later(key):
    provider = get_provider(key)

    assert provider.rule_driven is True
    assert provider.checkout_instalments == 0
    assert provider.start_rule == "months_after_purchase"
    assert provider.start_offset_months == 1


def test_atome_charges_the_first_instalment_on_the_purchase_date():
    atome = get_provider("atome")

    assert atome.rule_driven is True
    assert atome.checkout_instalments == 1
    assert atome.start_rule == "purchase_date"
    assert atome.start_offset_months == 0


def test_other_provider_has_no_rules_and_no_fee_formula():
    other = get_provider("other")

    assert other.rule_driven is False
    assert other.checkout_instalments == 0
    assert other.monthly_fee_applies is False


@pytest.mark.parametrize("unknown", ["grab_paylater", "boost", "", "SPayLater "])
def test_unknown_keys_behave_as_other(unknown):
    assert get_provider(unknown).key == "other"


def test_provider_labels_are_user_facing_names():
    assert [p.label for p in PROVIDERS.values()] == [
        "SPayLater",
        "TikTok PayLater",
        "Atome",
        "Other provider",
    ]


def test_keys_match_every_provider_check_constraint_in_the_migration():
    sql = MIGRATION.read_text(encoding="utf-8")
    lists = re.findall(r"provider in \(([^)]*)\)", sql)

    assert len(lists) >= 2  # bnpl_plans and provider_limits
    for raw in lists:
        assert set(re.findall(r"'([a-z_]+)'", raw)) == set(PROVIDER_KEYS)
