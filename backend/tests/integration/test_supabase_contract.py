"""Runs the repository contract against the REAL Supabase project: `uv run pytest -m integration`.

These tests are the only check that tests/fakes.py behaves like PostgREST and that the migration's
constraints (composite foreign keys, checks, unique index, row cap) hold. They create throwaway
users with random usernames and delete them (rows cascade) afterwards.
"""

import secrets

import pytest
from postgrest import APIError

from app.core.settings import MissingSettingsError, load_settings
from app.db import user_settings, users
from app.db.base import PAGE_SIZE, ScopedTable
from app.db.client import build_client

pytestmark = pytest.mark.integration

FK_VIOLATION = "23503"
CHECK_VIOLATION = "23514"


@pytest.fixture(scope="module")
def db():
    try:
        settings = load_settings()
    except MissingSettingsError as err:
        pytest.skip(f"no Supabase credentials configured: {err}")
    return build_client(settings)


@pytest.fixture
def two_users(db):
    created = [
        users.create(db, username=f"it_{secrets.token_hex(6)}", display_name=f"IT {n}")
        for n in ("A", "B")
    ]
    yield created
    for user in created:
        db.table("users").delete().eq("id", user["id"]).execute()


def _txn(**extra):
    return {"date": "2026-01-05", "amount_sen": 1000, "type": "expense", "category": "Food"} | extra


def _plan(**extra):
    return {
        "item_name": "Phone",
        "provider": "atome",
        "provider_label": "Atome",
        "total_price_sen": 90000,
        "num_installments": 3,
        "first_payment_date": "2026-02-01",
    } | extra


def test_username_lookup_is_case_insensitive_and_unique(db, two_users):
    amir = two_users[0]

    assert users.get_by_username(db, amir["username"].upper())["id"] == amir["id"]
    with pytest.raises(users.UsernameTakenError):
        users.create(db, username=amir["username"].upper(), display_name="Dup")


def test_wildcard_usernames_match_nothing(db, two_users):
    assert users.get_by_username(db, "%") is None
    assert users.get_by_username(db, "it_%") is None


def test_default_settings_row_uses_ledger_mode(db, two_users):
    settings = user_settings.create_default(db, two_users[0]["id"])

    assert settings["ledger_mode"] is True
    assert settings["current_balance_sen"] == 0


def test_rows_are_isolated_between_users(db, two_users):
    a, b = (u["id"] for u in two_users)
    table = ScopedTable(db, "transactions")
    mine = table.insert(a, _txn())
    table.insert(b, _txn(amount_sen=2000))

    assert [r["id"] for r in table.list_rows(a)] == [mine["id"]]
    assert table.get(b, mine["id"]) is None
    assert table.update(b, mine["id"], {"amount_sen": 1}) is None
    assert table.delete(b, mine["id"]) is False
    assert table.get(a, mine["id"])["amount_sen"] == 1000
    assert mine["is_bnpl"] is False and mine["source"] == "manual"  # database defaults


def test_a_transaction_cannot_link_to_another_users_plan(db, two_users):
    a, b = (u["id"] for u in two_users)
    plan_of_b = ScopedTable(db, "bnpl_plans").insert(b, _plan())

    with pytest.raises(APIError) as err:
        ScopedTable(db, "transactions").insert(a, _txn(bnpl_plan_id=plan_of_b["id"]))

    assert err.value.code == FK_VIOLATION


def test_deleting_a_plan_keeps_its_transactions_but_unlinks_them(db, two_users):
    a = two_users[0]["id"]
    plan = ScopedTable(db, "bnpl_plans").insert(a, _plan())
    txn = ScopedTable(db, "transactions").insert(a, _txn(bnpl_plan_id=plan["id"]))

    assert ScopedTable(db, "bnpl_plans").delete(a, plan["id"]) is True

    kept = ScopedTable(db, "transactions").get(a, txn["id"])
    assert kept is not None and kept["bnpl_plan_id"] is None and kept["user_id"] == a


def test_check_constraints_reject_bad_money(db, two_users):
    a = two_users[0]["id"]

    with pytest.raises(APIError) as err:
        ScopedTable(db, "transactions").insert(a, _txn(amount_sen=0))

    assert err.value.code == CHECK_VIOLATION


def test_malformed_ids_are_not_found_rather_than_errors(db, two_users):
    a = two_users[0]["id"]

    assert ScopedTable(db, "transactions").get(a, "not-a-uuid") is None


def test_list_rows_returns_more_rows_than_the_postgrest_cap(db, two_users):
    a = two_users[0]["id"]
    table = ScopedTable(db, "transactions")
    total = PAGE_SIZE + 250
    db.table("transactions").insert(
        [_txn(amount_sen=n + 1, user_id=a) for n in range(total)]
    ).execute()

    rows = table.list_rows(a, order_by="amount_sen")

    assert len(rows) == total
    assert [r["amount_sen"] for r in rows] == list(range(1, total + 1))
