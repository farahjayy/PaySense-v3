from pathlib import Path

import pytest

from ml.uat.load import UatDataError
from ml.uat.roster import load_roster

ROOT = Path(__file__).resolve().parents[4]
HEAD = "participant,username,display,persona\n"


def roster(tmp_path, body: str) -> Path:
    path = tmp_path / "testers.csv"
    path.write_text(HEAD + body, encoding="utf-8")
    return path


def test_the_committed_template_is_a_valid_roster():
    testers = load_roster(ROOT / "uat" / "testers.template.csv")
    assert {t.persona for t in testers} == {"frequent_bnpl", "budget_conscious", "irregular_income"}


def test_a_good_roster_is_parsed_in_order(tmp_path):
    testers = load_roster(
        roster(tmp_path, "P01,amir01,Amir,frequent_bnpl\nP02,sara02,Sara,budget_conscious\n")
    )
    assert [t.participant for t in testers] == ["P01", "P02"]
    assert testers[1].display == "Sara"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("P01,bad name,Amir,frequent_bnpl\n", "not allowed"),
        ("P01,amir,Amir,gamer\n", "persona must be"),
        ("P01,amir,,frequent_bnpl\n", "required"),
        ("P01,amir,A,frequent_bnpl\nP02,AMIR,B,budget_conscious\n", "duplicate"),
        ("P01,amir,A,frequent_bnpl\nP01,sara,B,budget_conscious\n", "duplicate"),
        ("", "no testers"),
    ],
)
def test_bad_rows_are_errors_that_say_why(tmp_path, body, message):
    with pytest.raises(UatDataError, match=message):
        load_roster(roster(tmp_path, body))


def test_wrong_header_is_rejected(tmp_path):
    path = tmp_path / "t.csv"
    path.write_text("name,persona\nA,frequent_bnpl\n", encoding="utf-8")
    with pytest.raises(UatDataError, match="header must be"):
        load_roster(path)
