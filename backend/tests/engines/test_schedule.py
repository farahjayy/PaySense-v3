"""D-57 scheduler: options over start dates x instalment counts, judged by the simulation."""

from datetime import date

from app.engines.risk.check import RiskRequest
from app.engines.risk.schedule import ADDED_MAX, Schedule, schedule

TODAY = date(2026, 1, 10)
PHONE = RiskRequest(provider="spaylater", item_name="Phone", purchase_date=TODAY,
                    num_installments=3, total_price_sen=79900)  # fmt: skip
INCOME = [date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)]


def fake(table):
    """evaluate(request) -> (with, without) from a {(purchase_date, count): with} table."""
    seen = []

    def evaluate(request):
        seen.append((request.purchase_date, request.num_installments))
        return table.get((request.purchase_date, request.num_installments), 0.9), 0.05

    return evaluate, seen


def test_the_first_option_in_order_that_adds_little_and_stays_below_at_risk_is_chosen():
    evaluate, seen = fake({(date(2026, 2, 2), 6): 0.08, (date(2026, 2, 2), 4): 0.12})
    out = schedule(evaluate, PHONE, INCOME)
    assert isinstance(out, Schedule) and out.chosen is not None
    # after the next income (the day after it), the count closest to 3 that qualifies: 4 adds 7
    # points (too many), 6 adds 3 (qualifies)
    assert (out.chosen.purchase_date, out.chosen.num_installments) == (date(2026, 2, 2), 6)
    assert out.chosen.added == 0.08 - 0.05 <= ADDED_MAX
    assert out.options[0].as_typed and out.options[0].purchase_date == TODAY
    assert seen[-1] == (date(2026, 2, 2), 6)  # the search stops at the first that qualifies


def test_the_order_is_date_first_then_the_count_closest_to_the_one_typed():
    evaluate, seen = fake({})
    schedule(evaluate, PHONE, INCOME)
    assert seen[:4] == [(TODAY, 3), (TODAY, 2), (TODAY, 4), (TODAY, 6)]
    assert {d for d, _ in seen} == {TODAY, date(2026, 2, 2), date(2026, 3, 2)}  # two income dates


def test_nothing_qualifies_when_the_student_is_already_at_risk_without_it():
    def evaluate(request):
        return 1.0, 1.0  # adds nothing, but the student is short on every path anyway

    out = schedule(evaluate, PHONE, INCOME)
    assert out.chosen is None and out.already_at_risk is True
    assert all(not o.qualifies for o in out.options)


def test_a_manual_plan_keeps_its_count_and_moves_its_first_payment_with_the_date():
    manual = RiskRequest(provider="other", item_name="Laptop", purchase_date=TODAY,
                         num_installments=4, instalment_sen=30000,
                         first_payment_date=date(2026, 2, 10))  # fmt: skip
    evaluate, seen = fake({})
    out = schedule(evaluate, manual, INCOME)
    assert {n for _, n in seen} == {4}
    moved = [o for o in out.options if o.purchase_date == date(2026, 2, 2)][0]
    assert moved.first_payment_date == date(2026, 3, 5)  # shifted by the same 23 days


def test_an_option_the_plan_rules_refuse_is_skipped():
    def evaluate(request):
        return None if request.num_installments == 2 else (0.06, 0.05)

    out = schedule(evaluate, PHONE, INCOME)
    assert out.chosen is not None and out.chosen.num_installments == 3
    assert all(o.num_installments != 2 for o in out.options)
