"""Backend for Playwright: the real app against the in-memory fake database.

    cd backend && uv run uvicorn tests.e2e_server:app --port 8100

It seeds one tester ("e2e") so the browser journey runs with no Supabase credentials, and signs
sessions with a random per-start key. Test tooling only — never deployed.
"""

import secrets
from datetime import date

from app.api.deps import get_today
from app.core.settings import Settings
from app.engines.risk.features import FEATURE_NAMES, FEATURE_SCHEMA_HASH
from app.main import create_app
from app.seed import seed_user
from tests.fakes import FakeSupabase

E2E_ORIGIN = "http://localhost:3100"
E2E_USERNAME = "e2e"
E2E_DISPLAY_NAME = "E2E Tester"
# The persona CSVs end on 28 December 2025; the browser tests run "the next day" so the imported
# ledger is fresh and the forecast is not flagged as out of date.
E2E_TODAY = date(2025, 12, 29)


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
        for journey in ("import", "screens", "risk", "spending")
    ]
    for username in usernames:
        seed_user(db, username=username, display_name=E2E_DISPLAY_NAME, persona="frequent_bnpl")
    app = create_app(settings, db=db, predictor=StubModel())
    app.dependency_overrides[get_today] = lambda: E2E_TODAY
    return app


app = build_e2e_app()
