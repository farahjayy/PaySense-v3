"""A request body is capped before it is buffered or parsed, and before login is checked
(P1 security review, HIGH): otherwise one unauthenticated POST could exhaust memory or disk."""

import pytest
from fastapi.testclient import TestClient

from app.core.body_limit import DEFAULT_LIMIT_BYTES, PER_PATH_LIMITS
from app.main import create_app

CSV_PATH = "/api/import/csv"


@pytest.fixture
def client(settings, fake_db_plain) -> TestClient:
    return TestClient(create_app(settings, db=fake_db_plain), raise_server_exceptions=False)


@pytest.fixture
def fake_db_plain():
    from tests.fakes import FakeSupabase

    return FakeSupabase()


def test_an_oversized_json_body_is_refused_by_its_declared_length(client):
    body = b'{"username":"' + b"a" * (DEFAULT_LIMIT_BYTES + 1) + b'"}'

    res = client.post("/api/auth/login", content=body, headers={"content-type": "application/json"})

    assert res.status_code == 413
    assert res.json()["detail"]["code"] == "payload_too_large"


def test_the_refusal_happens_before_authentication(client):
    res = client.post(
        "/api/import/confirm",
        content=b"x" * (DEFAULT_LIMIT_BYTES + 1),
        headers={"content-type": "application/json"},
    )

    assert res.status_code == 413  # not 401: nobody got to read the body or check a login


def test_a_chunked_body_without_a_content_length_is_cut_off_as_it_streams(client):
    def chunks():
        for _ in range(DEFAULT_LIMIT_BYTES // 65536 + 2):
            yield b"a" * 65536

    res = client.post(
        "/api/auth/login", content=chunks(), headers={"content-type": "application/json"}
    )

    assert res.status_code == 413
    assert res.json()["detail"]["code"] == "payload_too_large"


def test_a_normal_body_is_unaffected(client):
    res = client.post(
        "/api/auth/login", json={"username": "nobody", "passphrase": "not the right one"}
    )

    assert res.status_code == 401  # reached the handler: unknown user, not a size problem


def test_the_csv_upload_gets_a_larger_allowance(client):
    assert PER_PATH_LIMITS[CSV_PATH] > DEFAULT_LIMIT_BYTES
    between = b"a" * (DEFAULT_LIMIT_BYTES + 1024)

    res = client.post(CSV_PATH, files={"file": ("a.csv", between, "text/csv")})

    assert res.status_code == 401  # allowed through to authentication, which then refuses


def test_the_csv_upload_is_still_capped(client):
    too_big = b"a" * (PER_PATH_LIMITS[CSV_PATH] + 1)

    res = client.post(CSV_PATH, files={"file": ("a.csv", too_big, "text/csv")})

    assert res.status_code == 413


def test_requests_without_a_body_are_untouched(client):
    assert client.get("/api/health").status_code == 200


def test_the_413_carries_cors_headers_for_an_allowed_origin(client):
    res = client.post(
        "/api/auth/login",
        content=b"x" * (DEFAULT_LIMIT_BYTES + 1),
        headers={"content-type": "application/json", "Origin": "http://localhost:3000"},
    )

    assert res.status_code == 413
    assert res.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_a_garbage_content_length_is_a_clean_400(client):
    res = client.post(
        "/api/auth/login",
        content=b"{}",
        headers={"content-length": "abc", "content-type": "application/json"},
    )

    assert res.status_code in (400, 422)
