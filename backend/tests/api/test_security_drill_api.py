"""D-58: POST /api/security/drill runs the drill in a sandbox and leaves the caller's data alone."""

import json


def test_the_drill_needs_a_session(api):
    assert api.post("/api/security/drill").status_code == 401


def test_the_drill_reports_every_class_and_no_harm(api, amir):
    res = api.post("/api/security/drill", headers=amir)
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["sandbox"] is True and out["model"] == "scripted_hostile"
    assert {t["attack_class"] for t in out["totals"]} == {
        "induced_transfers",
        "data_extraction",
        "privilege_escalation",
        "prompt_injection",
    }
    assert all(t["attacks"] >= 3 and t["harmed"] == 0 for t in out["totals"])
    assert all(a["fooled"] for a in out["attacks"])


def test_the_callers_own_data_is_never_touched(api, amir, fake_db):
    body = {"date": "2025-12-05", "amount_sen": 500, "type": "expense", "category": "Food"}
    assert api.post("/api/transactions", json=body, headers=amir).status_code == 201
    before = json.dumps({t: fake_db.rows(t) for t in sorted(fake_db.tables)}, default=str,
                        sort_keys=True)  # fmt: skip
    assert api.post("/api/security/drill", headers=amir).status_code == 200
    after = json.dumps({t: fake_db.rows(t) for t in sorted(fake_db.tables)}, default=str,
                       sort_keys=True)  # fmt: skip
    assert after == before


def test_the_drill_is_rate_limited(api, amir):
    codes = [api.post("/api/security/drill", headers=amir).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
