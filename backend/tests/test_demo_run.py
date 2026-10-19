"""WP9: the demo run drives the whole story through the API and keeps what it saw."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.e2e_server import E2E_TODAY, build_e2e_app

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


demo_run, loader = _load("demo_run"), _load("load_personas")


def test_the_demo_runs_every_step_and_writes_its_evidence(tmp_path):
    app = build_e2e_app()
    app.state.llm = None  # guided mode: no model, so the run is deterministic
    with TestClient(app) as client:
        loader.run(app.state.db, client, session=E2E_TODAY, accounts_file=tmp_path / "a.json",
                   personas=sorted(loader.PERSONAS))  # fmt: skip
        accounts = loader.read_accounts(tmp_path / "a.json")
        auths = {
            p: loader.login(client, a["username"], a["passphrase"]) for p, a in accounts.items()
        }
        meta = demo_run.run(client, auths, E2E_TODAY, where="a test app", pause=0,
                            sleep=lambda _: None, out=tmp_path / "out")  # fmt: skip
    transcript = json.loads((tmp_path / "out" / "transcript.json").read_text(encoding="utf-8"))
    steps = transcript["steps"]
    assert {s["step"] for s in steps} >= {str(n) for n in range(10)}
    assert all(s["http_status"] < 500 for s in steps)
    assert transcript["plans_unchanged"] is True
    assert transcript["assistant"].startswith("guided mode")
    assert meta["steps"] == len(steps)
    audit = json.loads((tmp_path / "out" / "audit_log.json").read_text(encoding="utf-8"))
    assert any(e["kind"] == "message" for e in audit["assistant_events"])
    summary = (tmp_path / "out" / "SUMMARY.md").read_text(encoding="utf-8")
    assert "demo_run.py" in summary and "| 9 |" in summary
    # the irregular_income account is left with no savings buffer, as it was found
    irregular = auths["irregular_income"]
    assert client.get("/api/settings", headers=irregular).json()["savings_buffer_sen"] == 0


def test_the_paste_repeats_the_newest_row_so_the_preview_has_a_duplicate():
    latest = {"date": "2025-12-20", "amount_sen": 1234, "description": "Kopitiam"}
    paste = demo_run.messy_paste(latest, E2E_TODAY)
    assert paste.splitlines()[-1] == "20/12/2025 Kopitiam RM12.34"
    assert len(paste.splitlines()) == 3


def test_a_confirmed_plan_reports_its_plan_and_saved_risk_check_ids():
    body = {"id": "a1", "type": "create_plan", "status": "confirmed",
            "plan": {"check_id": "c1", "plan": {"id": "p1"}}, "message": "ok"}  # fmt: skip
    entry = {"step": "3", "what": "Confirm", "http_status": 200, "seconds": 0.1, "response": body}
    assert demo_run.summarise(entry)["ids"] == {"action": "a1", "plan": "p1", "risk_report": "c1"}


def _demo_app(tmp_path):
    app = build_e2e_app()
    app.state.llm = None
    client = TestClient(app)
    loader.run(app.state.db, client, session=E2E_TODAY, accounts_file=tmp_path / "a.json",
               personas=sorted(loader.PERSONAS))  # fmt: skip
    accounts = loader.read_accounts(tmp_path / "a.json")
    auths = {p: loader.login(client, a["username"], a["passphrase"]) for p, a in accounts.items()}
    return app, client, auths


def test_a_second_run_does_not_pile_up_the_demo_phone_plan(tmp_path):
    """Mock panel finding 4: the real account held three RM799 plans from three runs."""
    app, client, auths = _demo_app(tmp_path)
    phone = {"provider": "spaylater", "item_name": "Phone", "purchase_date": E2E_TODAY.isoformat(),
             "num_installments": 3, "total_price_sen": demo_run.DEMO_PRICE_SEN}  # fmt: skip
    with client:
        for _ in range(2):  # what earlier runs left behind
            res = client.post("/api/plans", json=phone, headers=auths["frequent_bnpl"])
            assert res.status_code == 201, res.text
        demo_run.run(client, auths, E2E_TODAY, where="a test app", pause=0,
                     sleep=lambda _: None, out=tmp_path / "out")  # fmt: skip
        plans = client.get("/api/plans", headers=auths["frequent_bnpl"]).json()
    assert sum(p["total_price_sen"] == demo_run.DEMO_PRICE_SEN for p in plans) <= 1


def test_a_failed_export_stops_the_run_instead_of_writing_an_empty_audit_log(tmp_path):
    app, client, auths = _demo_app(tmp_path)
    limiter = app.state.request_limiter
    allow = limiter.allow
    limiter.allow = lambda key, *a: (False, 3600) if key.startswith("export:") else allow(key, *a)
    with client, pytest.raises(SystemExit, match="export"):
        demo_run.run(client, auths, E2E_TODAY, where="a test app", pause=0,
                     sleep=lambda _: None, out=tmp_path / "out")  # fmt: skip
    assert not (tmp_path / "out" / "audit_log.json").exists()
