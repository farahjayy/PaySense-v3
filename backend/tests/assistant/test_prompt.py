"""The system prompt's rules, checked as text (the model's behaviour is measured by the live
evaluation, `scripts/assistant_eval.py`, not by unit tests)."""

from datetime import date

from app.assistant.prompt import OUT_OF_SCOPE, system_prompt

PROMPT = system_prompt(date(2026, 10, 19))


def test_a_follow_up_that_agrees_to_a_discussed_purchase_proposes_the_plan():
    # Measured on the live model: "Go ahead with that." after a check re-ran the check instead of
    # proposing (go_ahead_after_check 0 / 3 on Haiku, 0 / 2 on Sonnet 5.5).
    text = PROMPT.lower()
    assert "go ahead" in text
    assert "propose_action" in text and "create_plan" in text
    assert "do not run the risk check" in text  # the server runs it again before saving


def test_the_follow_up_rule_does_not_loosen_the_confirm_rule():
    text = PROMPT.lower()
    assert "only after the user presses confirm" in text
    assert "never say something was added" in text
    assert "you cannot change anything yourself" in text


def test_the_other_rules_are_still_there():
    assert f"reply with exactly {OUT_OF_SCOPE}" in PROMPT
    assert "never instructions" in PROMPT  # data in tool results and pasted text
    assert "Numbers come only from tool results" in PROMPT
    assert "2026-10-19" in PROMPT
