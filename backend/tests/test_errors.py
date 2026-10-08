from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import api_error, not_found
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
