from datetime import date, timedelta

import pytest

from app.engines.forecasting.recurring import Suggestion, detect, normalise_merchant


def row(day, amount, description, kind="expense", category="Bills", **extra):
    return {
        "date": day,
        "amount_sen": amount,
        "type": kind,
        "category": category,
        "description": description,
        **extra,
    }


def monthly(
    description,
    amount,
    months=4,
    day=5,
    kind="expense",
    start=date(2025, 1, 1),
    category="Bills",
    **extra,
):
    rows = []
    for i in range(months):
        month = start.month - 1 + i
        rows.append(
            row(
                date(start.year + month // 12, month % 12 + 1, day),
                amount,
                description,
                kind,
                category,
                **extra,
            )
        )
    return rows


def by_name(suggestions):
    return {s.name: s for s in suggestions}


def test_merchant_text_is_normalised_so_references_and_dates_do_not_split_a_group():
    assert normalise_merchant("Netflix subscription 0412") == normalise_merchant(
        "NETFLIX  Subscription 0531"
    )
    assert normalise_merchant("TNG eWallet RM  - 12/03") == "tng ewallet rm"
    assert normalise_merchant(None) == ""


def test_a_monthly_bill_is_suggested_with_its_amount_cadence_and_latest_date():
    found = by_name(detect(monthly("Sewa bilik", 45000, day=1)))

    s = found["sewa bilik"]
    assert (s.kind, s.cadence, s.amount_sen, s.occurrences) == ("bill", "monthly", 45000, 4)
    assert s.anchor_date == date(2025, 4, 1)


def test_a_weekly_and_a_biweekly_pattern_are_recognised():
    weekly = [row(date(2025, 1, 6) + timedelta(days=7 * i), 5000, "Gym pass") for i in range(6)]
    biweekly = [
        row(date(2025, 1, 3) + timedelta(days=14 * i), 80000, "Gaji part time", "income", "Salary")
        for i in range(4)
    ]

    found = by_name(detect(weekly + biweekly))

    assert found["gym pass"].cadence == "weekly" and found["gym pass"].kind == "bill"
    assert (
        found["gaji part time"].cadence == "biweekly" and found["gaji part time"].kind == "income"
    )


def test_two_occurrences_are_not_enough():
    assert detect(monthly("Spotify", 1590, months=2)) == []


def test_a_merchant_visited_at_irregular_gaps_is_not_a_bill():
    days = [
        date(2025, 1, 3),
        date(2025, 1, 9),
        date(2025, 2, 21),
        date(2025, 2, 23),
        date(2025, 4, 2),
    ]

    assert detect([row(d, 1200, "Kedai makan lunch", category="Food") for d in days]) == []


def test_a_regular_visit_with_wildly_different_amounts_is_not_a_bill():
    amounts = [1500, 9800, 2300, 15000]
    rows = [
        row(date(2025, i + 1, 10), a, "Mr DIY purchase", category="Shopping")
        for i, a in enumerate(amounts)
    ]

    assert detect(rows) == []


def test_amounts_within_fifteen_percent_still_count_and_the_median_is_reported():
    rows = [
        row(date(2025, i + 1, 14), a, "Unifi Mobile Bill")
        for i, a in enumerate([13500, 14500, 15200, 14100])
    ]

    (s,) = detect(rows)

    assert s.amount_sen == 14300  # median of the four


def test_refunds_transfers_and_plan_payments_are_never_suggested():
    rows = (
        monthly("Refund from Shopee", 2000, category="Refund", kind="income")
        + monthly("Top up own account", 5000, category="Transfer")
        + monthly("SPayLater instalment 1/3", 8000, category="BNPL", bnpl_plan_id="p1")
    )

    assert detect(rows) == []


def test_an_item_the_user_already_confirmed_is_not_suggested_again():
    rows = monthly("Sewa bilik", 45000)

    assert detect(rows, confirmed_names=["Sewa Bilik"]) == []


def test_income_and_expense_with_the_same_text_are_separate_groups():
    rows = monthly("Duit", 30000, kind="income", category="Allowance") + monthly("Duit", 3000)

    kinds = sorted(s.kind for s in detect(rows))

    assert kinds == ["bill", "income"]


def test_a_missed_month_does_not_break_a_pattern_that_otherwise_holds():
    rows = monthly("Astro subscription", 9900, months=6)
    del rows[3]

    (s,) = detect(rows)

    assert s.cadence == "monthly" and s.occurrences == 5


def test_a_semester_pattern_needs_three_occurrences_about_six_months_apart():
    rows = [
        row(d, 250000, "PTPTN disbursement", "income", "Allowance")
        for d in (date(2024, 3, 10), date(2024, 9, 10), date(2025, 3, 10))
    ]

    (s,) = detect(rows)

    assert s.cadence == "semester" and s.kind == "income"


def test_suggestions_are_deterministic_and_ordered():
    rows = monthly("Sewa bilik", 45000) + monthly("Spotify Premium", 1590)

    assert detect(rows) == detect(list(reversed(rows)))
    assert [s.name for s in detect(rows)] == sorted(s.name for s in detect(rows))


def test_the_ledger_is_not_modified():
    rows = monthly("Sewa bilik", 45000)
    before = [dict(r) for r in rows]

    detect(rows)

    assert rows == before


def test_confidence_is_higher_for_a_cleaner_pattern():
    clean = monthly("Sewa bilik", 45000)
    messy = [
        row(date(2025, 1, 5), 45000, "Gym"),
        row(date(2025, 2, 9), 41000, "Gym"),
        row(date(2025, 3, 8), 47500, "Gym"),
        row(date(2025, 4, 10), 44000, "Gym"),
    ]

    (a,) = detect(clean)
    (b,) = detect(messy)

    assert isinstance(a, Suggestion) and a.confidence > b.confidence


# --- scored against the generator's own ground truth (a test may import ml/, app/ may not) ---
PRECISION_FLOOR = 0.85
RECALL_FLOOR = 0.75  # stated before measuring (execution doc, P4)
DETECTABLE = {"weekly", "biweekly", "monthly"}  # a semester item needs ~18 months of history


@pytest.fixture(scope="module")
def scored():
    from ml.datagen.params import load_params
    from ml.datagen.profile import generate_profile

    params = load_params()
    true_pos = false_pos = false_neg = 0
    for index in range(60):
        profile = generate_profile(params, 11, index, history_months=4)
        rows = [t.as_row() for t in profile.transactions]
        truth = {
            (normalise_merchant(t.name), t.cadence)
            for t in profile.recurring_truth
            if t.cadence in DETECTABLE
        }
        found = {(normalise_merchant(s.name), s.cadence) for s in detect(rows)}
        true_pos += len(found & truth)
        false_pos += len(found - truth)
        false_neg += len(truth - found)
    return true_pos, false_pos, false_neg


def test_precision_and_recall_against_the_generators_recurring_truth(scored):
    true_pos, false_pos, false_neg = scored
    precision = true_pos / (true_pos + false_pos)
    recall = true_pos / (true_pos + false_neg)

    counts = f"tp={true_pos} fp={false_pos} fn={false_neg}"
    print(f"precision={precision:.3f} recall={recall:.3f} ({counts})")
    assert precision >= PRECISION_FLOOR and recall >= RECALL_FLOOR
