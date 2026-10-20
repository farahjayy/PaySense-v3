"""D-71: DB_BACKEND=memory starts the API on the in-memory database with the demo personas loaded,
so local development needs no Supabase project."""

from datetime import date

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.db.local_demo import DEMO_USERS, build_local_demo_db
from app.main import create_app

TODAY = date(2026, 10, 20)


def test_each_demo_persona_is_loaded_and_ends_the_day_before_today():
    db = build_local_demo_db("local-demo-passphrase", TODAY)
    for username in DEMO_USERS:
        user = next(u for u in db.rows("users") if u["username"] == username)
        mine = [r for r in db.rows("transactions") if r["user_id"] == user["id"]]
        assert len(mine) > 100
        latest = max(date.fromisoformat(str(r["date"])) for r in mine)
        assert 0 < (TODAY - latest).days <= 7


def test_a_memory_backend_app_logs_a_demo_persona_in():
    settings = Settings(_env_file=None, db_backend="memory", session_secret="s" * 32,
                        cors_origins="http://localhost:3000",
                        local_demo_passphrase="local-demo-passphrase")  # fmt: skip
    client = TestClient(create_app(settings))
    res = client.post("/api/auth/login",
                      json={"username": "aina", "passphrase": "local-demo-passphrase"})  # fmt: skip
    assert res.status_code == 200, res.text
    auth = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert client.get("/api/account/consent", headers=auth).json()["accepted"] is True
