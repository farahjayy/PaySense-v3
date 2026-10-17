"""Spending insights (WP14)."""

from app.domain.breakdown import category_breakdown
from app.domain.flows import month_summary
from app.domain.insights import MIN_HISTORY, spending_insights


def txn(day, amount, category="Food", kind="expense", row_id=None, description=None, **extra):
    return {
        "id": row_id or f"{day}-{category}-{amount}",
        "date": day,
        "amount_sen": amount,
        "type": kind,
        "category": category,
        "description": description,
        **extra,
    }


def income(day, amount):
    return txn(day, amount, "Allowance", kind="income")


def test_a_first_month_has_no_comparison():
    rows = [income("2026-02-01", 100_000), txn("2026-02-05", 20_000)]
    out = spending_insights(rows, "2026-02")
    assert out.previous_month is None
    (food,) = out.categories
    assert (food.status, food.previous_sen, food.change_pct) == ("new", 0, None)
    assert out.movers == []


def test_changes_against_last_month_including_new_and_gone():
    rows = [
        txn("2026-01-05", 20_000, "Food"),
        txn("2026-01-06", 5_000, "Gym"),
        txn("2026-01-07", 3_000, "Transport"),
        txn("2026-02-05", 26_000, "Food"),
        txn("2026-02-06", 9_000, "Shopping"),
        txn("2026-02-07", 3_000, "Transport"),
    ]
    out = spending_insights(rows, "2026-02")
    assert out.previous_month == "2026-01"
    by = {c.category: c for c in out.categories}
    assert (by["Food"].status, by["Food"].change_sen, by["Food"].change_pct) == ("up", 6000, 0.3)
    assert (by["Shopping"].status, by["Shopping"].change_pct) == ("new", None)
    assert (by["Gym"].status, by["Gym"].spend_sen, by["Gym"].change_sen) == ("gone", 0, -5000)
    assert by["Transport"].status == "same"
    assert [m.category for m in out.movers] == ["Shopping", "Food", "Gym"]


def test_totals_equal_the_month_summary_with_refunds_and_transfers():
    rows = [
        income("2026-02-01", 100_000),
        txn("2026-02-05", 30_000, "Shopping"),
        txn("2026-02-06", 10_000, "Refund", kind="income"),
        txn("2026-02-07", 50_000, "Transfer"),
        txn("2026-02-08", 5_000, "Savings", kind="savings"),
    ]
    out = spending_insights(rows, "2026-02")
    summary = month_summary(rows)[0]
    assert (out.income_sen, out.spend_sen) == (summary.income_sen, summary.spend_sen)
    assert out.spend_sen == 20_000
    assert out.savings_sen == 5_000
    assert out.left_over_sen == 80_000
    assert out.savings_rate == 0.8
    assert out.set_aside_rate == 0.05
    assert {c.category for c in out.categories} == {"Shopping"}  # refunds/transfers are not rows
    assert (
        sum(c.spend_sen for c in out.categories)
        == category_breakdown(rows, "2026-02").gross_spend_sen
    )


def test_no_income_means_no_rate():
    out = spending_insights([txn("2026-02-05", 1000)], "2026-02")
    assert out.savings_rate is None and out.set_aside_rate is None


def test_an_unusual_transaction_is_flagged_against_the_persons_own_history():
    history = [txn(f"2026-01-{d:02d}", amount, "Food") for d, amount in
               zip(range(2, 12), [1000, 1100, 900, 1000, 1200, 950, 1050, 1000, 1100, 1000],
                   strict=True)]  # fmt: skip
    month = [txn("2026-02-03", 1150, "Food"), txn("2026-02-04", 9000, "Food", row_id="big",
                                                  description="Buffet")]  # fmt: skip
    out = spending_insights(history + month, "2026-02")
    (flag,) = out.unusual
    assert (flag.transaction_id, flag.amount_sen, flag.description) == ("big", 9000, "Buffet")
    assert flag.median_sen == 1000
    assert flag.threshold_sen > 1150
    assert out.mad_k == 3.0


def test_too_little_history_is_not_judged_and_says_so():
    rows = [txn("2026-01-05", 1000, "Food")] * (MIN_HISTORY - 1) + [
        txn("2026-02-05", 50_000, "Food")
    ]
    out = spending_insights(rows, "2026-02")
    assert out.unusual == []
    assert "not enough history" in (out.unusual_note or "").lower()


def test_plan_payments_are_never_unusual():
    history = [txn(f"2026-01-{d:02d}", 1000, "BNPL", is_bnpl=True) for d in range(2, 12)]
    history += [txn(f"2026-01-{d:02d}", 1000 + d, "BNPL", is_bnpl=True) for d in range(12, 20)]
    month = [txn("2026-02-03", 90_000, "BNPL", is_bnpl=True)]
    out = spending_insights(history + month, "2026-02")
    assert out.unusual == []


def test_the_headline_rules_in_order():
    nothing = spending_insights([], "2026-02")
    assert nothing.headline_rule == "no_data"
    over = spending_insights([income("2026-02-01", 10_000), txn("2026-02-02", 15_000)], "2026-02")
    assert over.headline_rule == "spent_more_than_income"
    assert "RM 50.00" in over.headline
    up = spending_insights(
        [income("2026-01-01", 100_000), txn("2026-01-02", 20_000, "Food"),
         income("2026-02-01", 100_000), txn("2026-02-02", 30_000, "Food")],
        "2026-02",
    )  # fmt: skip
    assert up.headline_rule == "category_up"
    assert "Food" in up.headline and "RM 100.00" in up.headline
    kept = spending_insights(
        [income("2026-01-01", 100_000), txn("2026-01-02", 20_000, "Food"),
         income("2026-02-01", 100_000), txn("2026-02-02", 20_500, "Food")],
        "2026-02",
    )  # fmt: skip
    assert kept.headline_rule == "kept_income"
    assert "80%" in kept.headline  # 795 of 1000 kept, rounded half up


def test_every_figure_in_the_headline_is_in_the_response():
    out = spending_insights(
        [income("2026-01-01", 100_000), txn("2026-01-02", 20_000, "Food"),
         income("2026-02-01", 100_000), txn("2026-02-02", 30_000, "Food")],
        "2026-02",
    )  # fmt: skip
    food = out.categories[0]
    assert food.change_sen == 10_000  # the RM 100.00 in the sentence
