"""Bill analysis (WP13): recurring bills, increases, collisions and the next 30 days."""

from datetime import date

from app.domain.bill_analysis import analyse_bills, monthly_cost

TODAY = date(2026, 3, 10)


def item(kind, name, amount, anchor, cadence="monthly", item_id=None, interval=None):
    return {
        "id": item_id or f"id-{name}",
        "kind": kind,
        "name": name,
        "match_text": name,
        "amount_sen": amount,
        "cadence": cadence,
        "anchor_date": anchor,
        "active": True,
        "custom_interval_days": interval,
    }


def plan(plan_id, label, item_name, instalments):
    return {
        "id": plan_id,
        "provider_label": label,
        "item_name": item_name,
        "installments": [
            {"seq": n, "due_date": d, "amount_sen": a, "is_paid": paid}
            for n, (d, a, paid) in enumerate(instalments, start=1)
        ],
    }


def test_monthly_cost_follows_the_cadence():
    assert monthly_cost(item("bill", "x", 1200, "2026-01-01")) == 1200
    assert monthly_cost(item("bill", "x", 1200, "2026-01-01", "weekly")) == 5200
    assert monthly_cost(item("bill", "x", 1200, "2026-01-01", "biweekly")) == 2600
    assert monthly_cost(item("bill", "x", 1200, "2026-01-01", "semester")) == 200
    assert monthly_cost(item("bill", "x", 3000, "2026-01-01", "custom", interval=30)) == 3044


def test_the_recurring_summary_and_its_share_of_income():
    items = [
        item("bill", "Rent bilik", 35000, "2026-01-05"),
        item("bill", "Unifi", 10000, "2026-01-20"),
        item("income", "Allowance", 90000, "2026-01-01"),
    ]
    result = analyse_bills(items, [], [], TODAY)
    assert result.recurring.count == 2
    assert result.recurring.monthly_total_sen == 45000
    assert result.recurring.monthly_income_sen == 90000
    assert result.recurring.bills_share == 0.5


def test_no_recurring_items_gives_empty_answers_not_errors():
    result = analyse_bills([], [], [], TODAY)
    assert result.recurring.count == 0
    assert result.recurring.monthly_income_sen is None
    assert result.recurring.bills_share is None
    assert (result.increases, result.collisions, result.upcoming) == ([], [], [])
    assert result.upcoming_total_sen == 0


def test_a_bill_that_went_up_is_reported_with_both_amounts():
    items = [item("bill", "Unifi", 10000, "2026-01-20")]
    rows = [
        {"date": "2026-01-20", "amount_sen": 9900, "type": "expense", "description": "UNIFI"},
        {"date": "2026-02-20", "amount_sen": 10900, "type": "expense", "description": "Unifi"},
        {"date": "2026-02-21", "amount_sen": 50000, "type": "expense", "description": "Other"},
    ]
    (inc,) = analyse_bills(items, [], rows, TODAY).increases
    assert (inc.previous_sen, inc.latest_sen, inc.change_sen) == (9900, 10900, 1000)
    assert inc.change_pct == round(1000 / 9900, 4)
    assert (inc.previous_date, inc.latest_date) == (date(2026, 1, 20), date(2026, 2, 20))


def test_a_bill_that_went_down_or_stayed_is_not_an_increase():
    items = [item("bill", "Unifi", 10000, "2026-01-20")]
    rows = [
        {"date": "2026-01-20", "amount_sen": 10900, "type": "expense", "description": "Unifi"},
        {"date": "2026-02-20", "amount_sen": 9900, "type": "expense", "description": "Unifi"},
    ]
    assert analyse_bills(items, [], rows, TODAY).increases == []


def test_a_row_linked_by_id_counts_whatever_its_description():
    items = [item("bill", "Gym", 5000, "2026-01-02", item_id="gym-1")]
    rows = [
        {"date": "2026-01-02", "amount_sen": 5000, "type": "expense", "recurring_item_id": "gym-1"},
        {"date": "2026-02-02", "amount_sen": 6000, "type": "expense", "description": "x",
         "recurring_item_id": "gym-1"},
    ]  # fmt: skip
    assert analyse_bills(items, [], rows, TODAY).increases[0].latest_sen == 6000


def test_collisions_across_providers_within_seven_days():
    plans = [
        plan("p1", "SPayLater", "Phone", [("2026-03-12", 26600, False)]),
        plan("p2", "Atome", "Shoes", [("2026-03-17", 6000, False)]),
        plan("p3", "TikTok PayLater", "Bag", [("2026-03-30", 4000, False)]),
    ]
    items = [item("bill", "Rent bilik", 35000, "2026-01-15")]
    result = analyse_bills(items, plans, [], TODAY)
    (collision,) = result.collisions
    assert [i.name for i in collision.items] == ["Phone", "Rent bilik", "Shoes"]
    assert collision.total_sen == 26600 + 35000 + 6000
    assert (collision.start, collision.end) == (date(2026, 3, 12), date(2026, 3, 18))
    assert {i.provider_label for i in collision.items if i.kind == "instalment"} == {
        "SPayLater",
        "Atome",
    }


def test_a_plan_paid_early_is_not_due_and_does_not_collide():
    plans = [
        plan("p1", "SPayLater", "Phone", [("2026-03-12", 26600, True)]),
        plan("p2", "Atome", "Shoes", [("2026-03-13", 6000, False)]),
    ]
    result = analyse_bills([], plans, [], TODAY)
    assert [i.name for i in result.upcoming] == ["Shoes"]
    assert result.collisions == []


def test_the_next_thirty_days_and_overdue_instalments():
    plans = [plan("p1", "Atome", "Shoes", [("2026-03-01", 6000, False), ("2026-04-01", 6000, False),
                                          ("2026-05-01", 6000, False)])]  # fmt: skip
    items = [item("bill", "Phone plan", 3000, "2026-01-25")]
    result = analyse_bills(items, plans, [], TODAY)
    assert [(i.name, i.due_date.isoformat(), i.overdue) for i in result.upcoming] == [
        ("Shoes", "2026-03-01", True),
        ("Phone plan", "2026-03-25", False),
        ("Shoes", "2026-04-01", False),
    ]
    assert result.upcoming_total_sen == 15000
    assert result.window_days == 30


def test_an_inactive_item_is_ignored():
    off = item("bill", "Old gym", 5000, "2026-01-12") | {"active": False}
    result = analyse_bills([off], [], [], TODAY)
    assert result.recurring.count == 0 and result.upcoming == []
