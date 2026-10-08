"""Backend for Playwright: the real app against the in-memory fake database.

    cd backend && uv run uvicorn tests.e2e_server:app --port 8100

It seeds one tester ("e2e") so the browser journey runs with no Supabase credentials, and signs
sessions with a random per-start key. Test tooling only — never deployed.
"""

import secrets

from app.core.settings import Settings
from app.main import create_app
from app.seed import seed_user
from tests.fakes import FakeSupabase

E2E_ORIGIN = "http://localhost:3100"
E2E_USERNAME = "e2e"
E2E_DISPLAY_NAME = "E2E Tester"


def build_e2e_app():
    settings = Settings(
        _env_file=None,
        supabase_url="https://e2e.invalid",
        supabase_service_key=secrets.token_urlsafe(16),
        session_secret=secrets.token_urlsafe(48),
        cors_origins=E2E_ORIGIN,
    )
    db = FakeSupabase()
    seed_user(db, username=E2E_USERNAME, display_name=E2E_DISPLAY_NAME, persona="frequent_bnpl")
    return create_app(settings, db=db)


app = build_e2e_app()
