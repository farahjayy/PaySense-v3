def test_health_returns_ok(client):
    res = client.get("/api/health")

    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_openapi_is_served(client):
    res = client.get("/openapi.json")

    assert res.status_code == 200
    assert "/api/health" in res.json()["paths"]
