"""Monthly bill grouping ("My bills"). v1's tests/test_bills.py re-expressed in sen."""

from datetime import date

from app.domain.bills import monthly_bills


def _plan(plan_id, item_name, instalments, provider="spaylater"):
    return {
        "id": plan_id,
        "item_name": item_name,
        "provider": provider,
        "provider_label": "SPayLater",
        "installments": [
            {"seq": seq, "due_date": due, "amount_sen": amount, "is_paid": paid}
            for seq, (due, amount, paid) in enumerate(instalments, start=1)
        ],
    }


def test_instalments_are_grouped_by_due_month_across_plans():
    plans = [
        _plan(
            "p1", "Earbuds", [(date(2026, 10, 1), 10000, False), (date(2026, 11, 1), 10000, False)]
        ),
        _plan("p2", "Phone", [(date(2026, 10, 15), 5000, False)]),
    ]

    months = {m["month"]: m for m in monthly_bills(plans, today=date(2026, 9, 26))["months"]}

    assert months["2026-10"]["total_due_sen"] == 15000
    assert months["2026-11"]["total_due_sen"] == 10000
    assert len(months["2026-10"]["items"]) == 2


def test_months_ordered_current_first_then_past_descending_then_future_ascending():
    plans = [
        _plan(
            "p1",
            "X",
            [
                (date(2026, 7, 1), 100, True),
                (date(2026, 8, 1), 100, True),
                (date(2026, 9, 1), 100, True),
                (date(2026, 10, 1), 100, False),
                (date(2026, 12, 1), 100, False),
            ],
        )
    ]

    result = monthly_bills(plans, today=date(2026, 9, 26))

    assert [m["month"] for m in result["months"]] == [
        "2026-09",
        "2026-08",
        "2026-07",
        "2026-10",
        "2026-12",
    ]


def test_is_current_flag_set_only_on_the_current_month():
    plans = [_plan("p1", "X", [(date(2026, 9, 1), 100, False), (date(2026, 10, 1), 100, False)])]

    result = monthly_bills(plans, today=date(2026, 9, 26))

    assert {m["month"]: m["is_current"] for m in result["months"]} == {
        "2026-09": True,
        "2026-10": False,
    }


def test_current_month_is_simply_omitted_when_nothing_is_due_that_month():
    """No synthetic RM0 row — a month only appears if a real instalment falls in it."""
    plans = [_plan("p1", "X", [(date(2026, 8, 1), 100, True), (date(2026, 11, 1), 100, False)])]

    result = monthly_bills(plans, today=date(2026, 9, 26))

    assert [m["month"] for m in result["months"]] == ["2026-08", "2026-11"]
    assert all(not m["is_current"] for m in result["months"])


def test_fully_paid_is_true_only_when_every_instalment_in_the_month_is_paid():
    plans = [
        _plan("p1", "Earbuds", [(date(2026, 10, 1), 10000, True), (date(2026, 10, 1), 5000, False)])
    ]

    month = monthly_bills(plans, today=date(2026, 9, 26))["months"][0]

    assert month["fully_paid"] is False
    assert month["paid_total_sen"] == 10000
    assert month["total_due_sen"] == 15000


def test_a_month_where_everything_is_paid_is_fully_paid():
    plans = [_plan("p1", "Earbuds", [(date(2026, 8, 1), 10000, True)])]

    month = monthly_bills(plans, today=date(2026, 9, 26))["months"][0]

    assert month["fully_paid"] is True
    assert month["has_overdue"] is False  # paid, so not overdue even though in the past


def test_has_overdue_flags_an_unpaid_instalment_past_its_due_date():
    plans = [_plan("p1", "Earbuds", [(date(2026, 8, 1), 10000, False)])]

    assert monthly_bills(plans, today=date(2026, 9, 26))["months"][0]["has_overdue"] is True


def test_no_plans_gives_an_empty_list():
    assert monthly_bills([], today=date(2026, 9, 26)) == {"months": []}


def test_items_carry_the_plan_and_instalment_they_belong_to():
    plans = [_plan("p1", "Earbuds", [(date(2026, 10, 1), 10000, False)])]

    item = monthly_bills(plans, today=date(2026, 9, 26))["months"][0]["items"][0]

    assert item == {
        "plan_id": "p1",
        "item_name": "Earbuds",
        "provider": "spaylater",
        "provider_label": "SPayLater",
        "seq": 1,
        "amount_sen": 10000,
        "due_date": "2026-10-01",
        "is_paid": False,
    }


def test_iso_string_due_dates_are_accepted():
    plans = [_plan("p1", "X", [("2026-10-01", 100, False)])]

    assert monthly_bills(plans, today=date(2026, 9, 26))["months"][0]["month"] == "2026-10"
