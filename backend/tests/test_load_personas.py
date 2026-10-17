"""The persona loader (WP1), run against the real app on the in-memory database."""

import importlib.util
import json
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.e2e_server import E2E_TODAY, build_e2e_app

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "load_personas.py"
spec = importlib.util.spec_from_file_location("load_personas", SCRIPT)
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


@pytest.fixture
def app():
    return build_e2e_app()


def _db(app):
    return app.state.db


def test_usernames_are_unguessable_and_valid():
    name = loader.new_username("frequent_bnpl")
    assert re.fullmatch(r"fbnpl-[0-9a-f]{16}", name)
    assert loader.new_username("frequent_bnpl") != name


def test_each_persona_is_seeded_imported_and_unlocks_the_forecast(app, tmp_path):
    accounts = tmp_path / "accounts.json"
    with TestClient(app) as client:
        results = loader.run(
            _db(app),
            client,
            session=E2E_TODAY,
            accounts_file=accounts,
            personas=list(loader.PERSONAS),
        )
    for summary in results.values():
        assert summary["created"] > 100
        assert summary["skipped"] == 0
        assert summary["forecast_status"] == "ok"
        assert summary["months_of_history"] >= 4
    stored = json.loads(accounts.read_text())
    assert set(stored) == set(loader.PERSONAS)


def test_a_second_run_reuses_the_accounts_and_imports_nothing(app, tmp_path):
    accounts = tmp_path / "accounts.json"
    with TestClient(app) as client:
        first = loader.run(
            _db(app), client, session=E2E_TODAY, accounts_file=accounts, personas=["frequent_bnpl"]
        )
        second = loader.run(
            _db(app), client, session=E2E_TODAY, accounts_file=accounts, personas=["frequent_bnpl"]
        )
    assert first["frequent_bnpl"]["created"] > 0
    assert second["frequent_bnpl"]["created"] == 0
    assert second["frequent_bnpl"]["duplicates"] == first["frequent_bnpl"]["previewed"]
    assert second["frequent_bnpl"]["recurring_confirmed"] == 0
    users = [u for u in _db(app).rows("users") if u["persona"] == "frequent_bnpl"]
    assert len([u for u in users if u["username"].startswith("fbnpl-")]) == 1


def test_a_failing_call_names_the_step(app):
    with TestClient(app) as client, pytest.raises(RuntimeError, match="login"):
        loader.login(client, "nobody-here", None)


def test_the_session_date_moves_the_ledger(app, tmp_path):
    with TestClient(app) as client:
        loader.run(
            _db(app),
            client,
            session=date(2026, 3, 2),
            accounts_file=tmp_path / "a.json",
            personas=["budget_conscious"],
        )
    latest = max(r["date"] for r in _db(app).rows("transactions"))
    assert "2026-02-22" <= latest <= "2026-03-01"
