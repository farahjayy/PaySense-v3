import httpx
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import api_error, not_found, unauthorized
from app.main import create_app


class Body(BaseModel):
    amount: int


def _client_with_routes(settings) -> TestClient:
    app = create_app(settings)
    router = APIRouter()

    @router.get("/boom-404")
    def boom_404():
        raise not_found("thing_missing", "No such thing.")

    @router.get("/boom-400")
    def boom_400():
        raise api_error(400, "bad_thing", "Nope.")

    @router.post("/echo")
    def echo(body: Body):
        return body

    @router.get("/crash")
    def crash():
        raise RuntimeError("secret internals")

    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_api_error_uses_the_envelope(settings):
    res = _client_with_routes(settings).get("/boom-404")

    assert res.status_code == 404
    assert res.json() == {"detail": {"code": "thing_missing", "message": "No such thing."}}


def test_validation_errors_use_the_envelope(settings):
    res = _client_with_routes(settings).post("/echo", json={"amount": "abc"})

    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["code"] == "validation_error"
    assert "amount" in detail["message"]


def test_unexpected_errors_do_not_leak_internals(settings):
    res = _client_with_routes(settings).get("/crash")

    assert res.status_code == 500
    assert res.json()["detail"]["code"] == "internal_error"
    assert "secret internals" not in res.text


def test_unknown_route_uses_the_envelope(settings):
    res = _client_with_routes(settings).get("/nope")

    assert res.status_code == 404
    assert res.json()["detail"] == {"code": "not_found", "message": "Not found."}


def test_wrong_method_uses_the_envelope(settings):
    res = _client_with_routes(settings).post("/api/health")

    assert res.status_code == 405
    assert res.json()["detail"]["code"] == "method_not_allowed"
    assert "allow" in res.headers  # framework headers are preserved


def test_a_crash_still_carries_cors_headers_for_an_allowed_origin(settings):
    res = _client_with_routes(settings).get("/crash", headers={"Origin": "http://localhost:3000"})

    assert res.status_code == 500
    assert res.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_a_crash_does_not_grant_cors_to_other_origins(settings):
    res = _client_with_routes(settings).get("/crash", headers={"Origin": "https://evil.example"})

    assert res.status_code == 500
    assert "access-control-allow-origin" not in res.headers


def test_database_outage_is_a_503_the_client_can_retry(settings):
    app = create_app(settings)

    @app.get("/db-down")
    def db_down():
        raise httpx.ConnectTimeout("timed out")

    res = TestClient(app, raise_server_exceptions=False).get("/db-down")

    assert res.status_code == 503
    assert res.json()["detail"]["code"] == "upstream_unavailable"


def test_malformed_json_gets_a_readable_message(settings):
    res = _client_with_routes(settings).post(
        "/echo", content="{not json", headers={"content-type": "application/json"}
    )

    assert res.status_code == 422
    assert res.json()["detail"] == {
        "code": "validation_error",
        "message": "Request body is not valid JSON.",
    }


def test_unauthorized_errors_advertise_the_bearer_scheme():
    err = unauthorized("not_authenticated", "Log in.")

    assert err.headers == {"WWW-Authenticate": "Bearer"}


def test_api_error_accepts_extra_headers():
    err = api_error(429, "slow_down", "Wait.", headers={"Retry-After": "30"})

    assert err.headers == {"Retry-After": "30"}
