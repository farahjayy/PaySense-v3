"""WP4a: every tool, run as one user, never sees another user's data (hard constraint 4)."""

import json

import pytest

from app.assistant import executor
from app.assistant.tools import MODEL_TOOLS
from app.db import budgets, transactions
from tests.assistant.conftest import load_persona, uid
from tests.assistant.test_tools import COMPUTE_TOOLS, READ_TOOLS

SECRET_TEXT = "AMIR-PRIVATE-MERCHANT"
SECRET_SEN = 7_777_777


@pytest.fixture
def amir_has_data(db):
    amir = uid(db, "amir")
    load_persona(db, amir)
    transactions.create(db, amir, date="2025-12-20", amount_sen=SECRET_SEN, type="expense",
                        category="Shopping", description=SECRET_TEXT)  # fmt: skip
    budgets.set_budget(db, amir, "Amir-only budget", 123_456)
    return amir


@pytest.mark.parametrize("name", sorted(READ_TOOLS | COMPUTE_TOOLS))
def test_siti_never_sees_amirs_data(db, make_ctx, amir_has_data, name):
    args, _ = (READ_TOOLS | COMPUTE_TOOLS)[name]
    record = executor.run_tool(make_ctx("siti"), name, args, caller="model")
    blob = json.dumps(record.data, default=str) + record.step.summary
    assert SECRET_TEXT not in blob
    assert str(SECRET_SEN) not in blob
    assert "Amir-only budget" not in blob
    assert amir_has_data not in blob


def test_every_tool_is_covered_by_the_isolation_test():
    assert set(MODEL_TOOLS) - set(READ_TOOLS) - set(COMPUTE_TOOLS) <= {
        "propose_action",
        "parse_pasted_transactions",
    }
