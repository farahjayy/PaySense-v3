"""WP18 (ADR D-49): per-user daily write quota, the ledger cap, transaction pagination and the
database lock that stops two workers creating the same plan."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.db import locks
from app.db import transactions as txn_repo
from app.main import create_app

# POSTs that compute or read and never change the user's data (plus login/logout themselves).
NOT_WRITES = {
    ("post", "/api/auth/login"),
    ("post", "/api/auth/google/exchange"),  # a sign-in, like login (ADR D-69)
    ("post", "/api/auth/signup"),  # no user yet; limited per address like login (D-73)
    ("post", "/api/auth/logout"),
    ("post", "/api/risk/check"),
    ("post", "/api/risk/schedule"),  # stateless, like the check (D-57)
    ("post", "/api/security/drill"),  # a throwaway sandbox; the caller's data is untouched (D-58)
    ("post", "/api/plans/preview"),
    ("post", "/api/import/csv"),
    ("post", "/api/assistant/chat"),
    ("post", "/api/assistant/run"),
    ("post", "/api/assistant/actions/{action_id}/decline"),
    ("post", "/api/budgets/suggest"),
    ("post", "/api/account/export"),
}
WRITE_METHODS = {"post", "put", "patch", "delete"}


def _write_operations(api: TestClient) -> list[tuple[str, str]]:
    spec = api.get("/openapi.json").json()
    return sorted(
        (method, path)
        for path, ops in spec["paths"].items()
        for method in ops
        if method in WRITE_METHODS and (method, path) not in NOT_WRITES
    )


@pytest.fixture
def no_quota(settings, fake_db):
    tight = settings.model_copy(update={"daily_write_quota": 0})
    return TestClient(create_app(tight, db=fake_db))


def test_every_write_route_counts_against_the_daily_quota(api, no_quota, fake_db):
    from tests.api.conftest import _headers

    auth = _headers(no_quota, "amir")
    operations = _write_operations(api)
    assert len(operations) > 20  # the enumeration really found the write routes
    refused = []
    for method, path in operations:
        url = path.replace("{", "").replace("}", "")  # any value: the quota is checked first
        res = no_quota.request(method.upper(), url, headers=auth, params={"category": "Food"})
        if res.status_code == 429 and res.json()["detail"]["code"] == "daily_write_quota":
            refused.append((method, path))
    missing = sorted(set(operations) - set(refused))
    assert missing == [], f"write routes without the daily write quota: {missing}"


def test_the_quota_counts_per_user_and_says_when_it_resets(settings, fake_db):
    from tests.api.conftest import _headers

    client = TestClient(
        create_app(settings.model_copy(update={"daily_write_quota": 2}), db=fake_db)
    )
    amir, siti = _headers(client, "amir"), _headers(client, "siti")
    body = {"date": "2026-01-05", "amount_sen": 500, "type": "expense", "category": "Food"}

    assert client.post("/api/transactions", json=body, headers=amir).status_code == 201
    assert client.post("/api/transactions", json=body, headers=amir).status_code == 201
    third = client.post("/api/transactions", json=body, headers=amir)
    assert third.status_code == 429
    assert third.json()["detail"]["code"] == "daily_write_quota"
    assert 0 < int(third.headers["retry-after"]) <= 24 * 3600
    assert client.post("/api/transactions", json=body, headers=siti).status_code == 201


def test_reads_do_not_use_the_quota(no_quota):
    from tests.api.conftest import _headers

    auth = _headers(no_quota, "amir")
    assert no_quota.get("/api/transactions", headers=auth).status_code == 200
    assert no_quota.get("/api/plans", headers=auth).status_code == 200


# ------------------------------------------------------------------ ledger cap
def test_a_full_ledger_refuses_one_more_row(api, amir, monkeypatch):
    monkeypatch.setattr(txn_repo, "MAX_LEDGER_ROWS", 3)
    body = {"date": "2026-01-05", "amount_sen": 500, "type": "expense", "category": "Food"}
    for _ in range(3):
        assert api.post("/api/transactions", json=body, headers=amir).status_code == 201

    res = api.post("/api/transactions", json=body, headers=amir)

    assert res.status_code == 413
    assert res.json()["detail"]["code"] == "ledger_full"


def test_an_import_that_would_overflow_the_ledger_writes_nothing(api, amir, fake_db, monkeypatch):
    monkeypatch.setattr(txn_repo, "MAX_LEDGER_ROWS", 4)
    rows = [
        {"date": f"2026-01-0{d}", "amount_sen": 100 * d, "type": "expense", "category": "Food"}
        for d in range(1, 6)
    ]

    res = api.post("/api/import/confirm", json={"rows": rows}, headers=amir)

    assert res.status_code == 413
    assert fake_db.rows("transactions") == []


def test_one_users_full_ledger_does_not_block_another(api, amir, siti, monkeypatch):
    monkeypatch.setattr(txn_repo, "MAX_LEDGER_ROWS", 1)
    body = {"date": "2026-01-05", "amount_sen": 500, "type": "expense", "category": "Food"}
    assert api.post("/api/transactions", json=body, headers=amir).status_code == 201
    assert api.post("/api/transactions", json=body, headers=amir).status_code == 413
    assert api.post("/api/transactions", json=body, headers=siti).status_code == 201


def test_a_second_import_while_one_is_being_written_is_refused(api, amir, fake_db):
    """Known risk 15: count and insert run under the per-user import lock, so parallel imports
    cannot each pass the cap check before the other writes."""
    user_id = api.get("/api/auth/me", headers=amir).json()["id"]
    rows = [{"date": "2026-01-05", "amount_sen": 500, "type": "expense", "category": "Food"}]
    assert locks.acquire(fake_db, user_id, "ledger_import")

    res = api.post("/api/import/confirm", json={"rows": rows}, headers=amir)

    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "import_in_progress"
    assert fake_db.rows("transactions") == []


def test_the_import_lock_is_released_after_each_import(api, amir, fake_db):
    rows = [{"date": "2026-01-05", "amount_sen": 500, "type": "expense", "category": "Food"}]
    assert api.post("/api/import/confirm", json={"rows": rows}, headers=amir).status_code == 200
    assert api.post("/api/import/confirm", json={"rows": rows}, headers=amir).status_code == 200
    assert fake_db.rows("user_locks") == []


# ------------------------------------------------------------------ pagination
def _seed_days(api, auth, days):
    for d in days:
        body = {"date": d, "amount_sen": 100, "type": "expense", "category": "Food"}
        assert api.post("/api/transactions", json=body, headers=auth).status_code == 201


def test_the_cursor_pages_through_without_overlap_or_gaps(api, amir):
    days = ["2026-01-05"] * 4 + ["2026-01-04"] * 3 + ["2026-01-02"] * 2
    _seed_days(api, amir, days)
    params = {"start": "2026-01-01", "end": "2026-01-31", "limit": 2}
    seen, pages, cursor = [], 0, None
    while True:
        query = params | ({"cursor": cursor} if cursor else {})
        page = api.get("/api/transactions", params=query, headers=amir).json()
        seen += page["transactions"]
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert pages == 5
    assert len({t["id"] for t in seen}) == len(days)
    assert [t["date"] for t in seen] == sorted([t["date"] for t in seen], reverse=True)


def test_a_cursor_cannot_be_forged_into_another_query(api, amir):
    res = api.get("/api/transactions", params={"cursor": "not-a-cursor"}, headers=amir)
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "invalid_cursor"


def test_pagination_stays_inside_the_users_own_rows(api, amir, siti):
    _seed_days(api, amir, ["2026-01-05"] * 3)
    _seed_days(api, siti, ["2026-01-05"] * 3)
    params = {"start": "2026-01-01", "end": "2026-01-31", "limit": 2}
    first = api.get("/api/transactions", params=params, headers=amir).json()
    second = api.get(
        "/api/transactions", params=params | {"cursor": first["next_cursor"]}, headers=siti
    ).json()
    siti_ids = {
        t["id"]
        for t in api.get("/api/transactions", params=params | {"limit": 50}, headers=siti).json()[
            "transactions"
        ]
    }  # noqa: E501
    assert {t["id"] for t in second["transactions"]} <= siti_ids


def test_the_limit_is_bounded(api, amir):
    assert api.get("/api/transactions", params={"limit": 501}, headers=amir).status_code == 422
    assert api.get("/api/transactions", params={"limit": 0}, headers=amir).status_code == 422


# ------------------------------------------------------------------ plan-create lock
def test_a_held_lock_refuses_a_second_plan_create(api, amir, fake_db):
    user_id = api.get("/api/auth/me", headers=amir).json()["id"]
    assert locks.acquire(fake_db, user_id, "plan_create")
    body = {
        "provider": "spaylater",
        "item_name": "Phone",
        "purchase_date": "2026-01-05",
        "num_installments": 3,
        "total_price_sen": 60000,
    }

    res = api.post("/api/plans", json=body, headers=amir)

    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "confirm_in_progress"
    locks.release(fake_db, user_id, "plan_create")
    assert api.post("/api/plans", json=body, headers=amir).status_code == 201


def test_a_lock_is_per_user(fake_db):
    amir = next(u for u in fake_db.rows("users") if u["username"] == "amir")["id"]
    siti = next(u for u in fake_db.rows("users") if u["username"] == "siti")["id"]
    assert locks.acquire(fake_db, amir, "plan_create")
    assert not locks.acquire(fake_db, amir, "plan_create")
    assert locks.acquire(fake_db, siti, "plan_create")


def test_an_abandoned_lock_is_taken_over(fake_db):
    amir = next(u for u in fake_db.rows("users") if u["username"] == "amir")["id"]
    old = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=locks.STALE_AFTER_SECONDS + 5)
    assert locks.acquire(fake_db, amir, "plan_create", now=old)
    assert locks.acquire(fake_db, amir, "plan_create")


def test_the_lock_is_released_even_when_the_create_fails(api, amir, fake_db):
    body = {
        "provider": "spaylater",
        "item_name": "Phone",
        "purchase_date": "2026-01-05",
        "num_installments": 99,  # invalid: refused inside the locked section or before it
        "total_price_sen": 60000,
    }
    api.post("/api/plans", json=body, headers=amir)
    assert fake_db.rows("user_locks") == []


def test_a_released_lock_only_removes_its_own_holder(fake_db):
    """WP8 review finding 7: a slow holder whose lock was taken over must not free the new one."""
    amir = next(u for u in fake_db.rows("users") if u["username"] == "amir")["id"]
    old = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=locks.STALE_AFTER_SECONDS + 5)
    slow = locks.acquire(fake_db, amir, "plan_create", now=old)
    fresh = locks.acquire(fake_db, amir, "plan_create")
    assert slow and fresh
    locks.release(fake_db, amir, "plan_create", slow)
    assert not locks.acquire(fake_db, amir, "plan_create")
    locks.release(fake_db, amir, "plan_create", fresh)
    assert locks.acquire(fake_db, amir, "plan_create")
