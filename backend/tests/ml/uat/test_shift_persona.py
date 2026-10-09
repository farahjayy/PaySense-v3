from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from ml.uat.load import UatDataError
from ml.uat.shift_persona import (
    DATE_FORMAT,
    PERSONA_DIR,
    main,
    read_rows,
    shift_rows,
    weeks_to_shift,
)


def row(day: str, desc: str = "x", amount: str = "-1.00") -> dict[str, str]:
    return {"Date": day, "Description": desc, "Amount": amount}


def as_date(text: str) -> date:
    return datetime.strptime(text, DATE_FORMAT).date()


def test_the_shift_is_a_whole_number_of_weeks_that_lands_just_before_the_session():
    last = date(2025, 12, 28)
    session = date(2026, 10, 9)
    weeks = weeks_to_shift(last, session)
    moved = last + timedelta(weeks=weeks)
    assert moved < session
    assert (session - moved).days <= 7
    assert moved.weekday() == last.weekday()


def test_every_date_moves_by_the_same_amount_and_nothing_else_changes():
    rows = [row("01/09/2025", "Rent", "-300.00"), row("28/12/2025", "Allowance", "800.00")]
    out = shift_rows(rows, date(2026, 3, 1))
    deltas = {
        (as_date(o["Date"]) - as_date(r["Date"])).days for o, r in zip(out, rows, strict=True)
    }
    assert len(deltas) == 1
    assert deltas.pop() % 7 == 0
    assert [(o["Description"], o["Amount"]) for o in out] == [
        ("Rent", "-300.00"),
        ("Allowance", "800.00"),
    ]
    assert rows[0]["Date"] == "01/09/2025"  # inputs are not changed


def test_a_session_before_the_data_ends_moves_it_backwards_not_forwards_past_the_session():
    out = shift_rows([row("28/12/2025")], date(2025, 6, 1))
    assert as_date(out[0]["Date"]) < date(2025, 6, 1)


def test_a_malformed_date_names_its_row():
    with pytest.raises(UatDataError, match=r"row 3: date '2025-12-28'"):
        shift_rows([row("01/09/2025"), row("2025-12-28")], date(2026, 1, 1))


def test_the_real_personas_shift_cleanly_and_keep_their_length():
    for name in ("frequent_bnpl", "budget_conscious", "irregular_income"):
        rows = read_rows(PERSONA_DIR / f"{name}.csv")
        out = shift_rows(rows, date(2026, 11, 3))
        assert len(out) == len(rows)
        assert max(as_date(r["Date"]) for r in out) < date(2026, 11, 3)


def test_main_writes_the_file_and_reports_the_new_end(tmp_path, capsys):
    out = tmp_path / "shifted.csv"
    code = main(["--persona", "budget_conscious", "--session", "2026-11-03", "--out", str(out)])
    assert code == 0
    assert out.read_text(encoding="utf-8").startswith("Date,Description,Amount")
    assert "the last transaction is 2026-" in capsys.readouterr().out


def test_main_reports_a_missing_file_without_a_traceback(tmp_path, capsys):
    code = main(["--csv", str(tmp_path / "none.csv"), "--out", str(tmp_path / "o.csv")])
    assert code == 2
    assert "Cannot shift" in capsys.readouterr().err


def test_a_file_with_the_wrong_header_is_rejected(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("when,what\n1,2\n", encoding="utf-8")
    with pytest.raises(UatDataError, match="header must be"):
        read_rows(Path(bad))
