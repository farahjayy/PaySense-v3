import csv
from datetime import date

import numpy as np
import openpyxl
import pytest

from ml.engine1_eval.data import Series, split_profiles, weekly_values
from ml.engine1_eval.loaders.berka import load_berka
from ml.engine1_eval.loaders.moneydata import load_moneydata
from ml.engine1_eval.loaders.synthetic import load_synthetic


def test_weekly_values_fills_quiet_weeks_with_explicit_zeros():
    events = [(date(2025, 1, 6), 100), (date(2025, 1, 21), 50)]  # Mon wk1, Tue wk3

    start, values = weekly_values(events, date(2025, 1, 6), date(2025, 1, 26))

    assert start == date(2025, 1, 6)
    assert list(values) == [100, 0, 50]


def test_only_complete_monday_to_sunday_weeks_are_kept():
    events = [(date(2025, 1, 1), 10), (date(2025, 1, 8), 20), (date(2025, 1, 30), 30)]

    start, values = weekly_values(events, date(2025, 1, 1), date(2025, 1, 30))

    # 1 Jan is a Wednesday and 30 Jan a Thursday: weeks of 6, 13 and 20 and 27 Jan; only the
    # complete ones (6 Jan to 26 Jan) are kept, so the 8 Jan event lands in the first week.
    assert start == date(2025, 1, 6)
    assert list(values) == [20, 0, 0]


def test_a_span_without_a_complete_week_gives_nothing():
    assert weekly_values([(date(2025, 1, 1), 5)], date(2025, 1, 1), date(2025, 1, 4)) is None


def test_a_series_knows_its_week_starts():
    series = Series("a", "spend", "test", date(2025, 1, 6), np.array([1.0, 2.0, 3.0]))

    assert series.week_starts()[-1] == date(2025, 1, 20)
    assert len(series) == 3


def test_profile_split_is_disjoint_deterministic_and_complete():
    train, test = split_profiles(100, seed=3, test_share=0.2)

    assert set(train).isdisjoint(test)
    assert sorted([*train, *test]) == list(range(100))
    assert len(test) == 20
    assert split_profiles(100, seed=3, test_share=0.2) == (train, test)
    assert split_profiles(100, seed=4, test_share=0.2) != (train, test)


def write_cohort(path, profiles):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["profile_index", "week_start", "discretionary_sen", "income_sen"])
        for index in profiles:
            for week in range(3):
                writer.writerow(
                    [index, date(2025, 1, 6 + 7 * week).isoformat(), 100 * (week + 1), 500]
                )


def test_the_synthetic_loader_yields_a_spend_and_an_income_series_per_profile(tmp_path):
    path = tmp_path / "weekly_series.csv"
    write_cohort(path, [0, 1, 2])

    series = list(load_synthetic(path))

    assert [(s.series_id, s.kind) for s in series] == [
        ("syn-0", "spend"),
        ("syn-0", "income"),
        ("syn-1", "spend"),
        ("syn-1", "income"),
        ("syn-2", "spend"),
        ("syn-2", "income"),
    ]
    assert list(series[0].values) == [100, 200, 300]
    assert list(series[1].values) == [500, 500, 500]
    assert series[0].start == date(2025, 1, 6) and series[0].source == "synthetic"


def test_the_synthetic_loader_can_keep_only_chosen_profiles(tmp_path):
    path = tmp_path / "weekly_series.csv"
    write_cohort(path, [0, 1, 2, 3])

    series = list(load_synthetic(path, profile_ids={1, 3}))

    assert {s.series_id for s in series} == {"syn-1", "syn-3"}


def test_the_synthetic_loader_rejects_a_gap_in_the_weeks(tmp_path):
    path = tmp_path / "weekly_series.csv"
    path.write_text(
        "profile_index,week_start,discretionary_sen,income_sen\n"
        "0,2025-01-06,1,1\n0,2025-01-20,1,1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="gap"):
        list(load_synthetic(path))


def make_workbook(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Anonymized Original with Catego"
    ws.append(
        [
            "Transaction Number",
            "Transaction Date",
            "Transaction Type",
            "Transaction Description",
            "Debit Amount",
            "Credit Amount",
            "Balance",
            "Category",
            "Location City",
            "Location Country",
        ]
    )
    for number, (day, debit, credit, category) in enumerate(rows, start=1):
        ws.append([number, day, "DEB", "X", debit, credit, 0, category, None, None])
    ws.append([None] * 10)
    wb.save(path)


def test_moneydata_becomes_weekly_spend_and_income_leaving_savings_out(tmp_path):
    path = tmp_path / "money.xlsx"
    make_workbook(
        path,
        [
            ("06/01/2025", 10.0, None, "Groceries"),
            ("08/01/2025", 3.11, None, "Savings"),  # savings sweeps are not spending
            ("13/01/2025", None, 200.0, "Incoming"),
            ("20/01/2025", 5.5, None, "Groceries"),
            ("27/01/2025", 1.0, None, "Groceries"),
            ("28/01/2025", None, 1.0, "Incoming"),
        ],
    )

    series = {s.kind: s for s in load_moneydata(path, expected_sha256=None)}

    assert series["spend"].start == date(2025, 1, 6)
    assert list(series["spend"].values) == [1000, 0, 550]  # pence; last partial week dropped
    assert list(series["income"].values) == [0, 20000, 0]
    assert series["spend"].source == "moneydata"


def write_berka(tmp_path, trans):
    account = tmp_path / "account.csv"
    account.write_text(
        "account_id,district_id,frequency,date\n1,1,POPLATEK MESICNE,1995-01-01\n", "utf-8"
    )
    path = tmp_path / "trans.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "trans_id",
                "account_id",
                "date",
                "type",
                "operation",
                "amount",
                "balance",
                "k_symbol",
                "bank",
                "account",
            ]
        )
        for i, row in enumerate(trans, start=1):
            writer.writerow([i, 1, *row[:2], "", row[2], 0, row[3], "", ""])
    return account, path


def test_berka_keeps_variable_spend_and_income_and_drops_the_fixed_payments(tmp_path):
    account, trans = write_berka(
        tmp_path,
        [
            ("1995-01-02", "PRIJEM", 1000, ""),  # credit: income
            ("1995-01-03", "VYDAJ", 100, ""),  # variable debit
            ("1995-01-04", "VYBER", 50, ""),  # cash withdrawal: variable
            ("1995-01-05", "VYDAJ", 700, "SIPO"),  # household standing order: fixed
            ("1995-01-06", "PRIJEM", 3, "UROK"),  # interest: not income
            ("1995-01-09", "VYDAJ", 10, ""),
            ("1995-01-16", "VYDAJ", 20, ""),
            ("1995-01-23", "VYDAJ", 5, ""),
            ("1995-01-30", "VYDAJ", 1, ""),
        ],
    )

    series = {s.kind: s for s in load_berka(account, trans, min_weeks=3)}

    assert series["spend"].series_id == "berka-1"
    assert series["spend"].start == date(1995, 1, 2)
    assert list(series["spend"].values)[:3] == [150, 10, 20]
    assert list(series["income"].values)[:2] == [1000, 0]


def test_berka_skips_accounts_with_too_few_weeks(tmp_path):
    account, trans = write_berka(
        tmp_path, [("1995-01-02", "PRIJEM", 1000, ""), ("1995-01-09", "VYDAJ", 10, "")]
    )

    assert list(load_berka(account, trans, min_weeks=10)) == []


def test_moneydata_refuses_a_file_that_does_not_match_the_published_checksum(tmp_path):
    path = tmp_path / "money.xlsx"
    make_workbook(path, [("06/01/2025", 10.0, None, "Groceries")])

    with pytest.raises(ValueError, match="checksum"):
        list(load_moneydata(path))


def test_berka_sampling_keeps_a_seeded_subset_of_eligible_accounts(tmp_path):
    account = tmp_path / "account.csv"
    trans = tmp_path / "trans.csv"
    account.write_text("account_id\n1\n2\n3\n4\n", encoding="utf-8")
    with trans.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "trans_id",
                "account_id",
                "date",
                "type",
                "operation",
                "amount",
                "balance",
                "k_symbol",
                "bank",
                "account",
            ]
        )
        n = 0
        for acct in (1, 2, 3):  # account 4 has no transactions at all
            for week in range(12):
                n += 1
                writer.writerow(
                    [
                        n,
                        acct,
                        date(1995, 1, 2)
                        .fromordinal(date(1995, 1, 2).toordinal() + 7 * week)
                        .isoformat(),
                        "VYDAJ",
                        "",
                        10,
                        0,
                        "",
                        "",
                        "",
                    ]
                )

    chosen = {s.series_id for s in load_berka(account, trans, min_weeks=5, sample=(2, 7))}
    again = {s.series_id for s in load_berka(account, trans, min_weeks=5, sample=(2, 7))}
    other = {s.series_id for s in load_berka(account, trans, min_weeks=5, sample=(2, 8))}

    assert chosen == again and len(chosen) == 2 and chosen <= {"berka-1", "berka-2", "berka-3"}
    assert other <= {"berka-1", "berka-2", "berka-3"}


def test_berka_rejects_a_non_finite_or_negative_amount(tmp_path):
    account, trans = write_berka(
        tmp_path, [("1995-01-02", "VYDAJ", float("nan"), ""), ("1995-01-12", "VYDAJ", 5, "")]
    )

    with pytest.raises(ValueError, match="unusable amount"):
        list(load_berka(account, trans, min_weeks=1))


def test_the_synthetic_loader_rejects_a_file_that_is_not_sorted_by_profile(tmp_path):
    path = tmp_path / "weekly_series.csv"
    path.write_text(
        "profile_index,week_start,discretionary_sen,income_sen\n"
        "1,2025-01-06,1,1\n0,2025-01-06,1,1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not sorted"):
        list(load_synthetic(path))
