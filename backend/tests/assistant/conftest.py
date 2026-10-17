"""Fixtures for the assistant: two users on the in-memory database, a tool context for each, and
a ledger long enough to unlock the forecast (the persona CSV, shifted to end before TODAY)."""

from datetime import date
from pathlib import Path

import pytest

from app.assistant.context import ToolContext
from app.db import transactions, users
from app.domain.csv_import import parse_csv
from app.seed import seed_user
from tests.api.conftest import amir, api, fake_db, siti  # noqa: F401  (HTTP-level fixtures)
from tests.e2e_server import StubModel
from tests.fakes import FakeSupabase

TODAY = date(2025, 12, 29)  # the persona CSVs end on 28 December 2025
PERSONA = Path(__file__).resolve().parents[3] / "data" / "personas" / "frequent_bnpl.csv"


def load_persona(db, user_id: str) -> None:
    preview = parse_csv(PERSONA.read_text(encoding="utf-8"))
    rows = [
        {
            "date": r.date,
            "amount_sen": r.amount_sen,
            "type": r.type,
            "category": r.category_guess,
            "description": r.description,
        }
        for r in preview.rows
    ]
    transactions.bulk_create(db, user_id, rows, source="csv")


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    seed_user(fake, username="amir", display_name="Amir", persona="frequent_bnpl")
    seed_user(fake, username="siti", display_name="Siti", persona="budget_conscious")
    return fake


def uid(db, name: str) -> str:
    return users.get_by_username(db, name)["id"]


@pytest.fixture
def make_ctx(db, settings):
    def make(name: str = "amir", predictor=None) -> ToolContext:
        return ToolContext(
            db=db,
            user_id=uid(db, name),
            today=TODAY,
            settings=settings,
            predictor=StubModel() if predictor is None else predictor,
        )

    return make
