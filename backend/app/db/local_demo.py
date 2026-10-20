"""DB_BACKEND=memory (ADR D-71): local development without a Supabase project.

The API runs on the in-memory database the tests use (`memory.py`), seeded with the three demo
personas, each with the passphrase from LOCAL_DEMO_PASSPHRASE and the privacy notice accepted.
Each persona's statement is moved by whole weeks (weekdays kept) to end before today, the same
shift `ml/uat/shift_persona.py` gives testers. Nothing survives a restart.
"""

from datetime import date, timedelta
from pathlib import Path

from app.db import transactions, user_settings
from app.db.memory import FakeSupabase
from app.domain.consent import CONSENT_VERSION
from app.domain.csv_import import parse_csv
from app.seed import seed_user

PERSONA_DIR = Path(__file__).resolve().parents[3] / "data" / "personas"
DEMO_USERS = {  # username -> (display name, persona)
    "aina": ("Aina (demo)", "frequent_bnpl"),
    "hafiz": ("Hafiz (demo)", "budget_conscious"),
    "meiling": ("Mei Ling (demo)", "irregular_income"),
}


def build_local_demo_db(passphrase: str, today: date) -> FakeSupabase:
    db = FakeSupabase()
    for username, (display_name, persona) in DEMO_USERS.items():
        user, _ = seed_user(db, username=username, display_name=display_name, persona=persona,
                            passphrase=passphrase)  # fmt: skip
        user_settings.accept_consent(db, user["id"], CONSENT_VERSION)
        rows = parse_csv((PERSONA_DIR / f"{persona}.csv").read_text(encoding="utf-8")).rows
        shift = timedelta(weeks=(today - timedelta(days=1) - max(r.date for r in rows)).days // 7)
        transactions.bulk_create(db, user["id"], [
            {"date": r.date + shift, "amount_sen": r.amount_sen, "type": r.type,
             "category": r.category_guess, "description": r.description}
            for r in rows
        ], source="csv")  # fmt: skip
    return db
