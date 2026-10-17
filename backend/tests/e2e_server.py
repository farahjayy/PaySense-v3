"""Backend for Playwright: the real app against the in-memory fake database.

    cd backend && uv run uvicorn tests.e2e_server:app --port 8100

It seeds one tester ("e2e") so the browser journey runs with no Supabase credentials, and signs
sessions with a random per-start key. Test tooling only — never deployed.

With `E2E_FAKE_LLM=1` the assistant runs on `ScriptedLLM`, a deterministic stand-in for the model
(never a real provider), for every tester except the `assistant-guided` ones, who keep guided mode.
"""

import os
import secrets
from datetime import date
from pathlib import Path

from app.api.assistant import get_llm
from app.api.deps import CurrentUser, get_today
from app.assistant.llm import LLMResponse, ToolCall
from app.core.settings import Settings
from app.db import transactions
from app.domain.csv_import import parse_csv
from app.engines.risk.features import FEATURE_NAMES, FEATURE_SCHEMA_HASH
from app.main import create_app
from app.seed import seed_user
from tests.fakes import TEST_PASSPHRASE, FakeSupabase, accept_test_consent, give_test_passphrase

E2E_ORIGIN = "http://localhost:3100"
E2E_USERNAME = "e2e"
E2E_DISPLAY_NAME = "E2E Tester"
E2E_PASSPHRASE = TEST_PASSPHRASE  # every browser-test account shares it (test tooling only)
# The persona CSVs end on 28 December 2025; the browser tests run "the next day" so the imported
# ledger is fresh and the forecast is not flagged as out of date.
E2E_TODAY = date(2025, 12, 29)
PERSONA_CSV = Path(__file__).resolve().parents[2] / "data" / "personas" / "frequent_bnpl.csv"
JOURNEYS = ("import", "screens", "risk", "spending", "logout", "consent",
            "assistant-guided", "assistant-llm")  # fmt: skip
# The demo purchase (work-packages.md section 6): an RM799 phone on SPayLater over 3 months.
PHONE = {"provider": "spaylater", "item_name": "Phone", "purchase_date": E2E_TODAY.isoformat(),
         "num_installments": 3, "total_price_sen": 79900}  # fmt: skip


class StubModel:
    """Stands in for the trained risk model in browser tests: risk is twice the ratio of one
    instalment to monthly income, so a pricey purchase on a short plan is At Risk and spreading it
    out helps. Test tooling only."""

    version = "e2e-stub"
    feature_schema_hash = FEATURE_SCHEMA_HASH
    _ratio = FEATURE_NAMES.index("instalment_to_income")
    _dsr = FEATURE_NAMES.index("dsr_with_purchase")

    def predict(self, vector):
        return min(1.0, vector[self._ratio] * 2.0)

    def contributions(self, vector):
        out = [0.0] * len(FEATURE_NAMES)
        out[self._dsr] = 0.05
        return out


class ScriptedLLM:
    """A deterministic model for the browser journey: it picks a tool from keywords in the latest
    message and narrates with no figures, so nothing it says can disagree with a tool. Test tooling
    only; it never touches the network."""

    provider = "fake"
    model = "e2e-scripted"

    def complete(self, system, messages, tools, *, max_output_tokens, timeout) -> LLMResponse:
        last = messages[-1]
        if last.role == "tool":
            done = {r.name for r in last.tool_results}
            if "propose_action" in done:
                return self._say("I have set that up as a proposal. Nothing changes until you "
                                 "press Confirm.")  # fmt: skip
            return self._say("Here is the risk check for the phone. Say go ahead and I will "
                             "propose the plan for you to confirm.")  # fmt: skip
        text = last.text.lower()
        if "go ahead" in text:
            return self._call("propose_action", {"type": "create_plan", "payload": PHONE})
        if "afford" in text:
            return self._call("check_purchase_risk", PHONE)
        return self._say("I can check a purchase, read your bills or look at your budgets.")

    @staticmethod
    def _say(text: str) -> LLMResponse:
        return LLMResponse(text=text, tool_calls=[], input_tokens=10, output_tokens=10)

    @staticmethod
    def _call(name: str, arguments: dict) -> LLMResponse:
        return LLMResponse(text="", tool_calls=[ToolCall("e2e-1", name, arguments)],
                           input_tokens=10, output_tokens=5)  # fmt: skip


def load_persona(db: FakeSupabase, username: str) -> None:
    """Give a tester the persona ledger up front (the assistant journeys start from a full one)."""
    preview = parse_csv(PERSONA_CSV.read_text(encoding="utf-8"))
    rows = [
        {"date": r.date, "amount_sen": r.amount_sen, "type": r.type,
         "category": r.category_guess, "description": r.description}
        for r in preview.rows
    ]  # fmt: skip
    user_id = next(u["id"] for u in db.rows("users") if u["username"] == username)
    transactions.bulk_create(db, user_id, rows, source="csv")


def build_e2e_app():
    settings = Settings(
        _env_file=None,
        supabase_url="https://e2e.invalid",
        supabase_service_key=secrets.token_urlsafe(16),
        session_secret=secrets.token_urlsafe(48),
        cors_origins=E2E_ORIGIN,
    )
    db = FakeSupabase()
    # One tester per browser project and journey, so parallel journeys never share a ledger.
    usernames = [E2E_USERNAME] + [
        f"{E2E_USERNAME}-{project}-{journey}"
        for project in ("desktop", "phone")
        for journey in JOURNEYS
    ]
    for username in usernames:
        seed_user(db, username=username, display_name=E2E_DISPLAY_NAME, persona="frequent_bnpl")
        give_test_passphrase(db, username)
        if not username.endswith("consent"):  # one account per project sees the notice
            accept_test_consent(db, username)
        if "-assistant-" in username:
            load_persona(db, username)
    app = create_app(settings, db=db, predictor=StubModel())
    app.dependency_overrides[get_today] = lambda: E2E_TODAY
    if os.environ.get("E2E_FAKE_LLM") == "1":
        scripted = ScriptedLLM()

        def e2e_llm(user: CurrentUser):
            return None if user.username.endswith("assistant-guided") else scripted

        app.dependency_overrides[get_llm] = e2e_llm
    return app


app = build_e2e_app()
