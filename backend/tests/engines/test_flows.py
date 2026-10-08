from dataclasses import dataclass
from datetime import date

from app.engines.forecasting.flows import known_flows, occurrences

START, END = date(2025, 2, 3), date(2025, 5, 4)


def item(
    kind="bill",
    amount=10000,
    cadence="monthly",
    anchor=date(2025, 1, 15),
    interval=None,
    active=True,
):
    return {
        "kind": kind,
        "amount_sen": amount,
        "cadence": cadence,
        "custom_interval_days": interval,
        "anchor_date": anchor,
        "active": active,
    }


def test_a_monthly_item_lands_on_its_day_each_month():
    days = occurrences(item(anchor=date(2025, 1, 15)), START, END)

    assert days == [date(2025, 2, 15), date(2025, 3, 15), date(2025, 4, 15)]


def test_a_31st_of_month_item_is_clamped_in_short_months_without_drifting():
    days = occurrences(item(anchor=date(2025, 1, 31)), date(2025, 2, 1), date(2025, 5, 31))

    assert days == [date(2025, 2, 28), date(2025, 3, 31), date(2025, 4, 30), date(2025, 5, 31)]


def test_weekly_and_biweekly_items_step_from_the_anchor():
    weekly = occurrences(item(cadence="weekly", anchor=date(2025, 1, 6)), START, date(2025, 2, 24))
    biweekly = occurrences(
        item(cadence="biweekly", anchor=date(2025, 1, 3)), START, date(2025, 3, 7)
    )

    assert weekly == [date(2025, 2, 3), date(2025, 2, 10), date(2025, 2, 17), date(2025, 2, 24)]
    assert biweekly == [date(2025, 2, 14), date(2025, 2, 28)]


def test_a_custom_cadence_uses_its_interval_and_a_semester_item_repeats_every_six_months():
    custom = occurrences(
        item(cadence="custom", interval=10, anchor=date(2025, 1, 1)), START, date(2025, 2, 25)
    )
    semester = occurrences(
        item(cadence="semester", anchor=date(2024, 9, 10)), START, date(2025, 12, 31)
    )

    assert custom == [date(2025, 2, 10), date(2025, 2, 20)]
    assert semester == [date(2025, 3, 10), date(2025, 9, 10)]


def test_an_anchor_in_the_future_starts_at_the_anchor():
    days = occurrences(item(anchor=date(2025, 4, 20)), START, END)

    assert days == [date(2025, 4, 20)]


def test_nothing_falls_outside_the_horizon_and_inactive_items_are_ignored():
    flows = known_flows([item(active=False)], [], START, END)

    assert all(m.bills_sen == 0 for m in flows.values())


def test_months_collect_income_bills_and_instalments_separately():
    items = [
        item("income", 100000, anchor=date(2025, 1, 1)),
        item("bill", 45000, anchor=date(2025, 1, 1)),
    ]
    plans = [
        {
            "installments": [
                {"seq": 1, "due_date": date(2025, 2, 20), "amount_sen": 8000, "is_paid": False},
                {"seq": 2, "due_date": date(2025, 3, 20), "amount_sen": 8000, "is_paid": False},
            ]
        }
    ]

    flows = known_flows(items, plans, START, END)

    assert flows["2025-03"].income_sen == 100000
    assert flows["2025-03"].bills_sen == 45000
    assert flows["2025-03"].instalments_sen == 8000
    assert flows["2025-02"].instalments_sen == 8000


def test_paid_instalments_are_not_counted_again():
    plans = [
        {
            "installments": [
                {"seq": 1, "due_date": date(2025, 2, 20), "amount_sen": 8000, "is_paid": True}
            ]
        }
    ]

    assert known_flows([], plans, START, END)["2025-02"].instalments_sen == 0


def test_an_overdue_unpaid_instalment_is_due_in_the_first_month_of_the_horizon():
    plans = [
        {
            "installments": [
                {"seq": 1, "due_date": date(2025, 1, 20), "amount_sen": 8000, "is_paid": False}
            ]
        }
    ]

    flows = known_flows([], plans, START, END)

    assert flows["2025-02"].instalments_sen == 8000


@dataclass(frozen=True)
class FakeInstalment:
    seq: int
    due_date: date
    amount_sen: int
    paid_at_checkout: bool = False


@dataclass(frozen=True)
class FakeProposal:
    purchase_date: date
    cash_at_purchase_sen: int
    instalments: tuple


def test_a_proposed_plan_adds_its_checkout_payment_in_the_purchase_month_and_its_instalments():
    proposal = FakeProposal(
        purchase_date=date(2025, 2, 10),
        cash_at_purchase_sen=10000,  # the part over the limit, paid at checkout
        instalments=(
            FakeInstalment(1, date(2025, 3, 10), 20000),
            FakeInstalment(2, date(2025, 4, 10), 20000),
        ),
    )

    flows = known_flows([], [], START, END, proposed=proposal)

    assert flows["2025-02"].instalments_sen == 10000
    assert flows["2025-03"].instalments_sen == 20000
    assert flows["2025-04"].instalments_sen == 20000


def test_an_instalment_paid_at_checkout_is_not_counted_twice():
    proposal = FakeProposal(
        purchase_date=date(2025, 2, 10),
        cash_at_purchase_sen=15000,  # already includes the instalment paid at checkout
        instalments=(
            FakeInstalment(1, date(2025, 2, 10), 15000, paid_at_checkout=True),
            FakeInstalment(2, date(2025, 3, 10), 15000),
        ),
    )

    flows = known_flows([], [], START, END, proposed=proposal)

    assert flows["2025-02"].instalments_sen == 15000
    assert flows["2025-03"].instalments_sen == 15000


def test_every_month_of_the_horizon_is_present_even_when_empty():
    flows = known_flows([], [], START, END)

    assert list(flows) == ["2025-02", "2025-03", "2025-04", "2025-05"]
    assert all(m.income_sen == m.bills_sen == m.instalments_sen == 0 for m in flows.values())


def test_the_inputs_are_not_modified():
    items = [item()]
    before = [dict(i) for i in items]

    known_flows(items, [], START, END)

    assert items == before
