"""The live-evaluation script (WP6), run here with a scripted model: no network."""

import importlib.util
import sys
from pathlib import Path

from app.assistant.llm import FakeLLM, call, say

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("assistant_eval", SCRIPTS / "assistant_eval.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def scripted(system, messages, tools):
    """A tidy model: answers each scenario the way the success criteria expect."""
    text = messages[-1].text if messages[-1].role == "user" else ""
    if messages[-1].role == "tool":
        return say("Done; see the card.")
    if "poem" in text:
        return say("OUT_OF_SCOPE")
    if text == "Can I afford a phone?":
        return say("Which provider and how many instalments?")
    phone = {"provider": "spaylater", "item_name": "Phone", "purchase_date": "2025-12-29",
             "num_installments": 3, "total_price_sen": 79900}  # fmt: skip
    if "Go ahead" in text:
        return call("propose_action", {"type": "create_plan", "payload": phone})
    if "RM799" in text:
        return call("check_purchase_risk", phone)
    if "owe" in text:
        return call("get_bill_analysis")
    if "How am I doing" in text:
        return call("get_recommendations")
    if "food budget" in text:
        return call(
            "propose_action",
            {"type": "set_budget", "payload": {"category": "Food", "limit_sen": 40000}},
        )
    if "nasi lemak" in text:
        return call(
            "propose_action",
            {
                "type": "add_transaction",
                "payload": {
                    "date": "2025-12-29",
                    "amount_sen": 1250,
                    "type": "expense",
                    "category": "Food",
                },
            },
        )
    if "transactions" in text:
        rows = [
            {"date": "2025-12-27", "amount_sen": 1500, "type": "expense"},
            {"date": "2025-12-28", "amount_sen": 850, "type": "expense"},
            {"date": "2025-12-28", "amount_sen": 4290, "type": "expense"},
        ]
        return call("parse_pasted_transactions", {"rows": rows})
    return say("Noted.")


def test_a_tidy_model_passes_every_scenario_and_a_report_is_rendered():
    outcomes, status = ev.run(1, 0, llm=FakeLLM([scripted] * 40), sleep=lambda _: None)
    failed = {o.scenario: o.reasons for o in outcomes if not o.success}
    assert failed == {}
    summary = ev.summarise(outcomes)
    assert summary["success"] == len(ev.SCENARIOS)
    page = ev.render(summary, status, 1, "2026-10-18")
    assert "assistant_eval.py --runs 1" in page and "| afford | 1/1 |" in page


def test_a_failing_model_is_reported_as_failing():
    outcomes, _ = ev.run(1, 0, llm=FakeLLM([say("I am not sure.")] * 40), sleep=lambda _: None)
    by = {o.scenario: o for o in outcomes}
    assert (
        not by["afford"].success and "none of ['check_purchase_risk'] ran" in by["afford"].reasons
    )
    assert not by["set_budget"].success
    assert by["ambiguous"].success is False  # no question mark
