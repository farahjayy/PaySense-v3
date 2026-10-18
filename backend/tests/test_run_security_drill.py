"""The security-drill evidence script (D-58): it reports what the drill returned."""

import importlib.util
from datetime import date
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_security_drill.py"
spec = importlib.util.spec_from_file_location("run_security_drill", SCRIPT)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


def test_the_page_is_generated_from_the_drill():
    result = script.run_drill()
    page = script.render(result, date(2026, 10, 18))
    assert "run_security_drill.py" in page and "do not edit by hand" in page
    for label in script.LABEL.values():
        assert f"| {label} |" in page
    total = sum(t["attacks"] for t in result["totals"])
    assert f"| **Total** | **{total}** |" in page
    assert page.count("\n| ") >= total + 4  # every attack has a row


def test_harm_is_shown_as_yes_when_the_drill_finds_it():
    result = {"totals": [{"attack_class": "prompt_injection", "attacks": 1, "fooled": 1,
                          "harmed": 1}],
              "attacks": [{"title": "T", "attack_class": "prompt_injection", "stopped_by": "S",
                           "evidence": "E", "harmed": True}]}  # fmt: skip
    assert "| **yes** |" in script.render(result, date(2026, 10, 18))
