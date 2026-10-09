"""The counterfactual search: the smallest change that reaches Safe, or an honest 'none does'."""

from dataclasses import replace
from datetime import date

import pytest

from app.engines.forecasting.models import MovingAverage
from app.engines.risk.check import RiskRequest, run_check
from app.engines.risk.counterfactual import (
    MAX_EVALUATIONS,
    OFFERED_COUNTS,
    candidates,
    search,
)
from tests.engines.test_check import StubPredictor
from tests.engines.test_summary import EXISTING, ITEMS, TODAY, ledger

BASE = RiskRequest(
    provider="spaylater",
    item_name="Laptop",
    purchase_date=TODAY,
    num_installments=3,
    total_price_sen=60000,
)
NEXT_INCOME = date(2025, 6, 1)


class Outcome:
    """A stand-in for a check result: just a probability."""

    def __init__(self, p):
        self.status = "ok"
        self.probability = p


def evaluator(rule):
    """Build an evaluate function from `rule(request) -> probability`, counting its calls."""
    calls = []

    def evaluate(request):
        calls.append(request)
        return Outcome(rule(request))

    evaluate.calls = calls
    return evaluate


def kinds(candidate):
    return sorted(change.kind for change in candidate.changes)


class TestCandidates:
    def test_single_changes_come_first_and_are_ordered_by_effort(self):
        found = candidates(BASE, NEXT_INCOME)
        singles = [c for c in found if len(c.changes) == 1]
        assert singles and found[: len(singles)] == singles  # one change before any two
        for group in (singles, found[len(singles) :]):
            assert [c.effort for c in group] == sorted(c.effort for c in group)

    def test_only_more_instalments_are_offered_and_never_the_current_count(self):
        counts = {
            c.request.num_installments
            for c in candidates(BASE, NEXT_INCOME)
            if kinds(c) == ["instalments"]
        }
        assert counts == {n for n in OFFERED_COUNTS if n > BASE.num_installments}

    def test_waiting_moves_the_purchase_to_the_day_after_the_next_income(self):
        waits = [c for c in candidates(BASE, NEXT_INCOME) if kinds(c) == ["wait"]]
        assert [w.request.purchase_date for w in waits] == [date(2025, 6, 2)]

    def test_no_next_income_means_no_wait_lever(self):
        assert not any("wait" in kinds(c) for c in candidates(BASE, None))

    def test_price_cuts_are_whole_sen_and_only_when_a_price_was_entered(self):
        cuts = {
            c.request.total_price_sen
            for c in candidates(BASE, NEXT_INCOME)
            if kinds(c) == ["price"]
        }
        assert cuts == {54000, 45000, 30000}
        manual = replace(
            BASE, provider="other", total_price_sen=None, instalment_sen=20000,
            first_payment_date=date(2025, 6, 12), provider_label="Grab",
        )  # fmt: skip
        assert not any("price" in kinds(c) for c in candidates(manual, NEXT_INCOME))

    def test_other_providers_are_tried_only_for_a_rule_driven_request(self):
        switched = {
            c.request.provider for c in candidates(BASE, NEXT_INCOME) if kinds(c) == ["provider"]
        }
        assert switched == {"tiktok_paylater", "atome"}
        manual = replace(
            BASE, provider="other", total_price_sen=None, total_payable_sen=60000,
            first_payment_date=date(2025, 6, 12), provider_label="Grab",
        )  # fmt: skip
        assert not any("provider" in kinds(c) for c in candidates(manual, NEXT_INCOME))

    def test_a_manual_request_keeps_its_own_amounts_when_the_start_moves(self):
        manual = replace(
            BASE, provider="other", total_price_sen=None, total_payable_sen=60000,
            first_payment_date=date(2025, 6, 12), provider_label="Grab",
        )  # fmt: skip
        wait = next(c for c in candidates(manual, NEXT_INCOME) if kinds(c) == ["wait"])
        assert wait.request.first_payment_date == date(2025, 7, 3)  # moved by the same 21 days
        assert wait.request.total_payable_sen == 60000

    def test_the_list_is_capped_and_has_no_duplicates(self):
        found = candidates(BASE, NEXT_INCOME)
        assert len(found) <= MAX_EVALUATIONS
        keys = [repr(c.request) for c in found]
        assert len(set(keys)) == len(keys)
        assert BASE not in [c.request for c in found]


class TestSearch:
    def test_a_purchase_that_is_already_safe_needs_no_change(self):
        evaluate = evaluator(lambda r: 0.04)
        result = search(BASE, NEXT_INCOME, evaluate)
        assert result.baseline_band == "Safe"
        assert result.reaches_safe and result.best.changes == ()
        assert len(evaluate.calls) == 1

    def test_a_longer_plan_makes_an_unaffordable_purchase_safe_and_the_smallest_one_is_chosen(self):
        # risk falls as instalments rise: 3 -> 0.5, 4 -> 0.25, 6 -> 0.08, 9 -> 0.03
        by_count = {3: 0.5, 4: 0.25, 6: 0.08, 9: 0.03, 12: 0.01, 2: 0.7}
        result = search(BASE, NEXT_INCOME, evaluator(lambda r: by_count[r.num_installments]))

        assert result.reaches_safe
        assert kinds(result.best) == ["instalments"]
        assert result.best.request.num_installments == 6  # not 9 or 12: the smallest that works
        assert result.best.probability == 0.08

    def test_a_price_cut_is_chosen_when_the_instalment_count_cannot_help(self):
        def rule(request):
            return 0.5 if request.total_price_sen > 45000 else 0.05

        result = search(BASE, NEXT_INCOME, evaluator(rule))
        assert result.reaches_safe
        assert kinds(result.best) == ["price"]
        assert result.best.request.total_price_sen == 45000  # the 25% cut, not the 50% one

    def test_two_small_changes_are_used_when_no_single_one_is_enough(self):
        def rule(request):
            more = request.num_installments >= 6
            cheaper = request.total_price_sen <= 54000
            return 0.05 if more and cheaper else 0.6

        result = search(BASE, NEXT_INCOME, evaluator(rule))
        assert result.reaches_safe
        assert kinds(result.best) == ["instalments", "price"]

    def test_when_nothing_reaches_safe_it_says_so_and_reports_the_best_it_found(self):
        def rule(request):
            return 0.9 - 0.2 * (request.total_price_sen <= 30000)

        result = search(BASE, NEXT_INCOME, evaluator(rule))
        assert not result.reaches_safe
        assert result.best is not None and result.best.probability == pytest.approx(0.7)
        assert result.best.request.total_price_sen == 30000
        assert result.evaluated <= MAX_EVALUATIONS

    def test_the_search_stops_at_the_first_combination_that_reaches_safe(self):
        evaluate = evaluator(lambda r: 0.05 if r.num_installments >= 4 else 0.5)
        result = search(BASE, NEXT_INCOME, evaluate)
        assert result.reaches_safe
        assert len(evaluate.calls) == 2  # the baseline, then the cheapest change, which works

    def test_candidates_the_plan_rules_reject_are_skipped_not_fatal(self):
        from app.domain.plan_builder import ProposalError

        def evaluate(request):
            if request.num_installments == 6:
                raise ProposalError("amount_too_small", "too small")
            return Outcome(0.5 if request.num_installments < 9 else 0.05)

        result = search(BASE, NEXT_INCOME, evaluate)
        assert result.reaches_safe and result.best.request.num_installments == 9

    def test_a_locked_ledger_gives_no_suggestion(self):
        class Locked:
            status = "locked"
            probability = None

        result = search(BASE, NEXT_INCOME, lambda r: Locked())
        assert result.baseline_band is None and result.best is None and not result.reaches_safe


def test_end_to_end_with_the_real_pipeline_and_a_stub_model_that_rewards_smaller_instalments():
    """A model whose risk is the instalment-to-income ratio (feature 9): more instalments help."""
    from app.engines.risk.features import FEATURE_NAMES

    column = FEATURE_NAMES.index("instalment_to_income")

    class Ratio:
        version = "ratio"

        def predict(self, vector):
            return min(1.0, vector[column] * 2.0)

    def evaluate(request):
        return run_check(
            rows=ledger(), items=ITEMS, plans=EXISTING, provider_limits={"spaylater": 900000},
            request=request, today=TODAY, forecaster=MovingAverage(8), predictor=Ratio(),
            paths=150, seed=3,
        )  # fmt: skip

    big = replace(BASE, total_price_sen=180000, num_installments=2)
    result = search(big, NEXT_INCOME, evaluate)

    assert result.baseline_band in ("Caution", "At Risk")
    assert result.reaches_safe
    assert result.best.request.num_installments > 2 or result.best.request.total_price_sen < 180000
    assert StubPredictor  # imported for parity with the check tests


class TestDescribe:
    def test_each_change_reads_as_one_sentence_with_only_its_own_number(self):
        from app.engines.risk.counterfactual import Change, describe

        assert describe(Change("instalments", 6)) == "Spread it over 6 instalments"
        assert describe(Change("wait", date(2025, 6, 2))) == (
            "Buy it on 2 June 2025, after your next income"
        )
        assert describe(Change("price", 45000)) == "Choose something priced at about RM 450"
        assert describe(Change("price", 123456)) == "Choose something priced at about RM 1,235"
        assert describe(Change("provider", "tiktok_paylater")) == "Use TikTok PayLater instead"

    def test_an_unknown_kind_is_an_error(self):
        from app.engines.risk.counterfactual import Change, describe

        with pytest.raises(ValueError):
            describe(Change("magic", 1))


def test_a_baseline_already_computed_is_not_computed_again():
    calls = []

    def evaluate(request):
        calls.append(request)
        return Outcome(0.05)

    result = search(BASE, NEXT_INCOME, evaluate, baseline=Outcome(0.5))
    assert result.baseline_band == "At Risk" and result.reaches_safe
    assert BASE not in calls  # the baseline was not asked for again
