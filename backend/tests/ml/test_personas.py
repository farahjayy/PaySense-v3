import hashlib
from pathlib import Path

import pytest

from app.domain.categorize import REFUND, TRANSFER
from app.domain.csv_import import parse_csv
from app.domain.flows import history_span, month_summary
from ml.datagen.params import load_params
from ml.datagen.personas import (
    PERSONA_SEEDS,
    build_persona_profile,
    render_csv,
    write_personas,
)

PARAMS = load_params()
PERSONAS = tuple(PERSONA_SEEDS)


@pytest.fixture(scope="module")
def profiles():
    return {persona: build_persona_profile(PARAMS, persona) for persona in PERSONAS}


def as_rows(preview):
    return [
        {
            "date": r.date,
            "amount_sen": r.amount_sen,
            "type": r.type,
            "category": r.category_guess,
        }
        for r in preview.rows
    ]


def test_each_persona_has_a_fixed_seed():
    assert set(PERSONA_SEEDS) == {"frequent_bnpl", "budget_conscious", "irregular_income"}


def test_the_csv_is_bank_style_with_signed_ringgit_amounts_and_dd_mm_yyyy_dates(profiles):
    text = render_csv(profiles["budget_conscious"])
    header, first, *_ = text.splitlines()

    assert header == "Date,Description,Amount"
    date_cell, _, amount = first.partition(",")[0], None, first.rsplit(",", 1)[1]
    assert len(date_cell) == 10 and date_cell[2] == "/" and date_cell[5] == "/"
    assert amount.lstrip("-").count(".") == 1 and len(amount.rsplit(".", 1)[1]) == 2


def test_rendering_is_reproducible(profiles):
    assert render_csv(profiles["frequent_bnpl"]) == render_csv(
        build_persona_profile(PARAMS, "frequent_bnpl")
    )


@pytest.mark.parametrize("persona", PERSONAS)
def test_the_importer_reads_every_row_without_skipping_any(profiles, persona):
    profile = profiles[persona]
    preview = parse_csv(render_csv(profile))

    assert preview.skipped == ()
    assert len(preview.rows) == len(profile.transactions)


@pytest.mark.parametrize("persona", PERSONAS)
def test_each_file_covers_at_least_four_distinct_months(profiles, persona):
    profile = profiles[persona]
    span = history_span(as_rows(parse_csv(render_csv(profile))), profile.as_of)

    assert span.distinct_months >= 4


@pytest.mark.parametrize("persona", PERSONAS)
def test_income_and_spend_survive_the_round_trip(profiles, persona):
    profile = profiles[persona]
    original = month_summary(t.as_row() for t in profile.transactions)
    imported = month_summary(as_rows(parse_csv(render_csv(profile))))

    assert [m.income_sen for m in imported] == [m.income_sen for m in original]
    assert [m.spend_sen for m in imported] == [m.spend_sen for m in original]


@pytest.mark.parametrize("persona", PERSONAS)
def test_the_file_includes_a_refund_and_an_own_account_transfer_on_purpose(profiles, persona):
    categories = {r["category"] for r in as_rows(parse_csv(render_csv(profiles[persona])))}

    assert {REFUND, TRANSFER} <= categories


def test_the_frequent_bnpl_persona_pays_bnpl_instalments(profiles):
    bnpl = [t for t in profiles["frequent_bnpl"].transactions if t.category == "BNPL"]

    assert len(bnpl) >= 3


def test_the_irregular_persona_is_paid_in_gigs_not_a_steady_allowance(profiles):
    gigs = [t for t in profiles["irregular_income"].transactions if t.category == "Gig"]

    assert len(gigs) >= 3


def test_no_amount_is_zero_and_nothing_is_dated_in_the_future(profiles):
    for profile in profiles.values():
        assert all(t.amount_sen > 0 and t.date <= profile.as_of for t in profile.transactions)


def test_writing_twice_produces_byte_identical_files(tmp_path):
    first = write_personas(PARAMS, tmp_path / "a")
    second = write_personas(PARAMS, tmp_path / "b")

    digests = lambda paths: [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths]  # noqa: E731
    assert digests(first) == digests(second)
    assert [Path(p).name for p in first] == [f"{persona}.csv" for persona in PERSONAS]


def test_files_use_unix_line_endings_and_no_byte_order_mark(tmp_path):
    for path in write_personas(PARAMS, tmp_path):
        raw = Path(path).read_bytes()
        assert b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf")
