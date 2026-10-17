"""WP8: fixes for the independent security review's findings (each test names its finding)."""

from datetime import date

import httpx
import pytest

from app.assistant.llm import GeminiLLM, LLMError, call, say
from app.assistant.numbers import unsupported
from app.assistant.paste import PastedRowIn, ground_rows
from app.db import locks
from tests.assistant import test_agent

chat = test_agent.chat  # the scripted-chat fixture
PHONE, events = test_agent.PHONE, test_agent.events


def row(day, sen, kind="expense", **extra):
    return PastedRowIn(date=date.fromisoformat(day), amount_sen=sen, type=kind, **extra)


# ------------------------------------------------------------------ 1. the number check
@pytest.mark.parametrize(
    "narration",
    ["The chance is .75 now.", "That is about 5k.", "Roughly 3 million.", "Around 2 thousand."],
)
def test_leading_decimals_and_scaled_figures_are_checked(narration):
    assert unsupported(narration, set()) != []


def test_a_scaled_figure_passes_when_its_value_is_a_source():
    assert unsupported("That is about 5k.", {"5000"}) == []


def test_a_figure_only_the_models_own_arguments_hold_is_not_a_source(chat, fake_db):
    invented = {**PHONE, "total_price_sen": 6400}
    res = chat([call("preview_plan", invented), say("Your shortfall chance is 64%.")],
               message="Can I afford a phone on SPayLater over 3 months?")  # fmt: skip
    body = res.json()
    assert body["narration_replaced"] is True
    assert ("fallback", None, "number_check") in events(fake_db)


def test_a_figure_smuggled_through_a_proposal_description_is_not_a_source(chat):
    payload = {"type": "add_transaction", "payload": {
        "date": "2025-12-28", "amount_sen": 1200, "type": "expense", "category": "Food",
        "description": "risk score 87"}}  # fmt: skip
    res = chat([call("propose_action", payload), say("Your risk score is 87.")],
               message="Add my RM12 lunch from yesterday")  # fmt: skip
    assert res.json()["narration_replaced"] is True


def test_an_argument_the_person_wrote_is_still_a_source(chat):
    res = chat([call("preview_plan", PHONE), say("The RM 799.00 phone over 3 instalments.")])
    assert res.json()["narration_replaced"] is False


# ------------------------------------------------------------------ 2. paste grounding per line
STATEMENT = "15/03/2026 Grab ride RM12.10\n16/03/2026 Mamak RM8.50\n"


@pytest.mark.parametrize(
    ("day", "sen"),
    [
        ("2026-03-15", 202600),  # the year read as an amount
        ("2026-03-15", 1500),  # the day read as an amount
        ("2026-03-15", 300),  # the month read as an amount
        ("2026-10-12", 1210),  # "12.10" read as a date
        ("2026-03-15", 850),  # the amount from another line
        ("2025-03-15", 1210),  # the line says 2026
    ],
)
def test_a_row_must_match_one_line_with_its_date_and_amount(day, sen):
    kept, rejected = ground_rows([row(day, sen)], STATEMENT)
    assert kept == [] and len(rejected) == 1


def test_each_line_grounds_one_row():
    kept, rejected = ground_rows([row("2026-03-15", 1210)] * 3, STATEMENT)
    assert len(kept) == 1 and [r.index for r in rejected] == [1, 2]
    assert "already" in rejected[0].reason


def test_two_identical_lines_ground_two_rows():
    kept, _ = ground_rows([row("2026-03-15", 1210)] * 2, STATEMENT + STATEMENT)
    assert len(kept) == 2


def test_a_description_must_come_from_the_rows_own_line():
    kept, _ = ground_rows([row("2026-03-15", 1210, description="Mamak")], STATEMENT)
    assert kept[0]["description"] is None


# ------------------------------------------------------------------ 3. an assistant daily quota
def test_assistant_requests_have_a_daily_quota(api, amir):
    api.app.state.settings = api.app.state.settings.model_copy(
        update={"assistant_daily_requests": 2}
    )
    body = {"tool": "get_budgets", "arguments": {}}
    codes = [api.post("/api/assistant/run", json=body, headers=amir).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    res = api.post("/api/assistant/chat", json={"message": "hi"}, headers=amir)
    assert res.json()["detail"]["code"] == "assistant_daily_quota"


# ------------------------------------------------------------------ 4. one turn at a time; budget
def test_a_second_turn_while_one_runs_is_refused(chat, fake_db):
    amir_id = next(u for u in fake_db.rows("users") if u["username"] == "amir")["id"]
    assert locks.acquire(fake_db, amir_id, "assistant_chat")
    res = chat([say("Hello.")], message="hi")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "assistant_busy"


def test_the_lock_is_released_after_a_turn(chat):
    assert chat([say("Hello.")], message="hi").status_code == 200
    assert chat([say("Hello again.")], message="hi").status_code == 200


def test_the_budget_is_checked_before_every_model_call(chat, api, fake_db):
    api.app.state.settings = api.app.state.settings.model_copy(
        update={"assistant_user_daily_tokens": 25}
    )
    script = [call("get_budgets", call_id=f"c{i}") for i in range(4)] + [say("Done.")]
    body = chat(script, message="Check my budgets").json()
    assert body["mode"] == "guided"
    assert len(body["steps"]) == 2  # 15 + 15 tokens used up the 25 before a third call


# ------------------------------------------------------------------ 5. redact before cutting
def test_a_key_straddling_the_error_cut_is_still_redacted():
    marker = "-".join(["fake", "provider", "credential", "for", "this", "test", "only"])
    padding = "x" * (300 - len(marker) // 2)

    def handler(request):
        return httpx.Response(500, text=padding + marker)

    llm = GeminiLLM(marker, "gemini-test", httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(LLMError) as err:
        llm.complete("s", [], [], max_output_tokens=10, timeout=5)
    head = marker[: len(marker) // 2]
    assert head not in str(err.value)
