"""The repayment-history flag: a rule over the user's own instalments, not a model input (D-11)."""

from datetime import date

import pytest

from app.engines.risk.repayment import (
    CONSECUTIVE_MISSES_WARNING,
    WINDOW_MONTHS,
    assess_repayment,
)

TODAY = date(2026, 10, 9)


def inst(plan, seq, due, paid=None, amount=10000):
    return {
        "plan_id": plan,
        "seq": seq,
        "due_date": due,
        "amount_sen": amount,
        "is_paid": paid is not None,
        "paid_date": paid,
    }


def test_no_plans_is_a_clean_record():
    flag = assess_repayment([], TODAY)
    assert flag.level == "none"
    assert flag.overdue_count == 0
    assert flag.late_paid_count == 0
    assert flag.longest_miss_run == 0


def test_instalments_paid_on_or_before_the_due_date_are_not_late():
    rows = [
        inst("a", 1, date(2026, 8, 1), paid=date(2026, 7, 30)),
        inst("a", 2, date(2026, 9, 1), paid=date(2026, 9, 1)),
        inst("a", 3, date(2026, 10, 1), paid=date(2026, 10, 1)),
    ]
    assert assess_repayment(rows, TODAY).level == "none"


def test_instalments_not_yet_due_are_not_misses():
    rows = [inst("a", 1, date(2026, 10, 9)), inst("a", 2, date(2026, 11, 9))]
    flag = assess_repayment(rows, TODAY)
    assert (flag.level, flag.overdue_count) == ("none", 0)


def test_one_overdue_instalment_is_a_watch_with_its_amount():
    rows = [inst("a", 1, date(2026, 9, 20), amount=15050), inst("a", 2, date(2026, 10, 20))]
    flag = assess_repayment(rows, TODAY)
    assert flag.level == "watch"
    assert (flag.overdue_count, flag.overdue_sen) == (1, 15050)
    assert flag.longest_miss_run == 1


def test_a_late_payment_inside_the_window_is_a_watch_but_one_outside_it_is_forgotten():
    recent = [inst("a", 1, date(2026, 8, 1), paid=date(2026, 8, 6))]
    old = [inst("a", 1, date(2026, 2, 1), paid=date(2026, 2, 20))]
    assert assess_repayment(recent, TODAY).level == "watch"
    assert assess_repayment(recent, TODAY).late_paid_count == 1
    assert assess_repayment(old, TODAY).level == "none"


def test_window_boundary_is_six_calendar_months_back_inclusive():
    assert WINDOW_MONTHS == 6
    edge = [inst("a", 1, date(2026, 4, 9), paid=date(2026, 4, 12))]
    out = [inst("a", 1, date(2026, 4, 8), paid=date(2026, 4, 12))]
    assert assess_repayment(edge, TODAY).late_paid_count == 1
    assert assess_repayment(out, TODAY).late_paid_count == 0


def test_three_consecutive_misses_in_one_plan_is_a_warning_citing_the_rule():
    assert CONSECUTIVE_MISSES_WARNING == 3
    rows = [
        inst("a", 1, date(2026, 7, 1), paid=date(2026, 7, 15)),  # paid late: not a miss
        inst("a", 2, date(2026, 8, 1)),  # overdue
        inst("a", 3, date(2026, 9, 1)),  # overdue
        inst("a", 4, date(2026, 10, 1)),  # overdue
    ]
    flag = assess_repayment(rows, TODAY)
    assert flag.level == "warning"
    assert flag.longest_miss_run == 3
    assert (flag.overdue_count, flag.late_paid_count) == (3, 1)
    assert "three" in flag.reason.lower()
    assert "Bank Negara" in flag.reason


def test_instalments_that_were_paid_late_are_never_called_missed():
    rows = [
        inst("a", s, date(2026, 6 + s, 1), paid=date(2026, 6 + s, 2)) for s in (1, 2, 3)
    ]  # three in a row, each paid a day late
    flag = assess_repayment(rows, TODAY)
    assert flag.level == "watch"
    assert (flag.late_paid_count, flag.longest_miss_run, flag.overdue_count) == (3, 0, 0)
    assert "missed" not in flag.reason.lower()


def test_an_instalment_still_unpaid_after_the_window_still_counts_as_overdue():
    rows = [inst("a", 1, date(2026, 2, 1))]  # eight months ago and never paid
    flag = assess_repayment(rows, TODAY)
    assert flag.level == "watch"
    assert (flag.overdue_count, flag.overdue_sen) == (1, 10000)


def test_a_run_of_misses_is_not_cut_short_by_the_window():
    rows = [inst("a", s, date(2026, 2 + s, 1)) for s in (1, 2, 3, 4)]  # Mar, Apr, May, Jun
    flag = assess_repayment(rows, TODAY)
    assert flag.level == "warning"
    assert flag.longest_miss_run == 4


def test_misses_that_are_not_consecutive_do_not_make_a_warning():
    rows = [
        inst("a", 1, date(2026, 7, 1)),  # overdue
        inst("a", 2, date(2026, 8, 1), paid=date(2026, 8, 1)),  # on time breaks the run
        inst("a", 3, date(2026, 9, 1)),  # overdue
    ]
    flag = assess_repayment(rows, TODAY)
    assert flag.level == "watch"
    assert flag.longest_miss_run == 1


def test_runs_are_counted_per_plan_not_across_plans():
    rows = [
        inst("a", 1, date(2026, 8, 1)),
        inst("a", 2, date(2026, 9, 1)),
        inst("b", 1, date(2026, 8, 5)),
        inst("b", 2, date(2026, 9, 5)),
    ]
    flag = assess_repayment(rows, TODAY)
    assert flag.level == "watch"
    assert flag.longest_miss_run == 2
    assert flag.overdue_count == 4


def test_input_order_does_not_matter_and_inputs_are_not_changed():
    rows = [
        inst("a", 3, date(2026, 9, 1)),
        inst("a", 1, date(2026, 7, 1)),
        inst("a", 2, date(2026, 8, 1)),
    ]
    snapshot = [dict(r) for r in rows]
    assert assess_repayment(rows, TODAY).level == "warning"
    assert rows == snapshot


def test_string_dates_from_the_database_are_accepted():
    rows = [{**inst("a", 1, "2026-09-01"), "due_date": "2026-09-01"}]
    assert assess_repayment(rows, TODAY).overdue_count == 1


@pytest.mark.parametrize("level", ["none", "watch", "warning"])
def test_every_level_has_a_plain_reason(level):
    rows = {
        "none": [],
        "watch": [inst("a", 1, date(2026, 9, 1))],
        "warning": [inst("a", s, date(2026, 6 + s, 1)) for s in (1, 2, 3)],
    }[level]
    flag = assess_repayment(rows, TODAY)
    assert flag.level == level
    assert flag.reason
