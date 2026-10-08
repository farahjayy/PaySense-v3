import pytest

from app.domain.money import format_rm, parse_rm, percent_to_hundredths


@pytest.mark.parametrize(
    ("text", "sen"),
    [
        ("0", 0),
        ("12", 1200),
        ("12.5", 1250),
        ("12.50", 1250),
        ("0.05", 5),
        ("1,234.56", 123456),
        ("1,234", 123400),
        ("RM 12", 1200),
        ("rm12.30", 1230),
        ("  RM1,000.00  ", 100000),
    ],
)
def test_parse_rm_reads_ringgit_text_exactly(text, sen):
    assert parse_rm(text) == sen


@pytest.mark.parametrize(
    "text",
    ["", "   ", "abc", "-5", "(12.00)", "12.345", "12.340", "1,23", "1,2345", ".5", "12.", "1 000"],
)
def test_parse_rm_rejects_anything_ambiguous(text):
    with pytest.raises(ValueError, match="amount"):
        parse_rm(text)


def test_parse_rm_never_goes_through_a_float():
    # 0.1 + 0.2 style traps: these amounts are not exactly representable as floats.
    assert parse_rm("0.29") == 29
    assert parse_rm("1.15") == 115
    assert parse_rm("4.35") == 435
    assert parse_rm("19.99") == 1999


@pytest.mark.parametrize(
    ("sen", "text"),
    [
        (0, "RM 0.00"),
        (5, "RM 0.05"),
        (1250, "RM 12.50"),
        (123456, "RM 1,234.56"),
        (100000000, "RM 1,000,000.00"),
        (-250, "-RM 2.50"),
    ],
)
def test_format_rm(sen, text):
    assert format_rm(sen) == text


@pytest.mark.parametrize("sen", [0, 1, 99, 100, 123456, 987654321])
def test_format_then_parse_round_trips(sen):
    assert parse_rm(format_rm(sen)) == sen


@pytest.mark.parametrize(
    ("rate", "hundredths"),
    [("1.5", 150), (0, 0), ("0", 0), (1.5, 150), ("2.505", 251), ("0.004", 0), (3, 300)],
)
def test_percent_to_hundredths_rounds_half_up_to_0_01_percent(rate, hundredths):
    assert percent_to_hundredths(rate) == hundredths


def test_percent_to_hundredths_rejects_negative_rates():
    with pytest.raises(ValueError, match="rate"):
        percent_to_hundredths("-1")


def test_absurdly_long_numbers_are_rejected_not_turned_into_huge_integers():
    with pytest.raises(ValueError, match="amount"):
        parse_rm("9" * 4000)
