"""WP4c / D-47: a figure in the narration must come from this turn's tool results, the server's
step summaries or the user's own message."""

import pytest

from app.assistant.numbers import allowed_figures, figures_of, normalise, unsupported

RISK = {
    "probability": 0.875578,
    "score": 12,
    "band": "At Risk",
    "plan": {"total_price_sen": 79900, "fee_sen": 0, "first_payment_date": "2026-11-18",
             "installments": [{"amount_sen": 26634}, {"amount_sen": 26633}]},
}  # fmt: skip


@pytest.mark.parametrize(("raw", "norm"), [("1,234.50", "1234.5"), ("12.00", "12"), ("007", "7"),
                                           ("0.5", "0.5"), ("266.34", "266.34")])  # fmt: skip
def test_normalise(raw, norm):
    assert normalise(raw) == norm


def test_sen_fields_allow_their_ringgit_forms_and_probabilities_their_percentages():
    figures = figures_of(RISK)
    assert {"799", "266.34", "266", "88", "87.6", "12", "2026", "11", "18"} <= figures


@pytest.mark.parametrize(
    "narration",
    [
        "This RM 799.00 phone is At Risk: an 88% chance of a shortfall, score 12.",
        "Each instalment is about RM 266.34, first due on 18 November 2026.",
        "Spread over 3 instalments it is still At Risk.",
    ],
)
def test_figures_from_the_tool_results_pass(narration):
    assert unsupported(narration, allowed_figures([RISK], [])) == []


@pytest.mark.parametrize(
    "narration",
    [
        "You can afford RM 450.00 a month.",  # invented
        "There is a 35% chance of a shortfall.",  # not the engine's figure
        "Your score would rise to 64 if you wait.",
    ],
)
def test_an_invented_figure_is_caught(narration):
    assert unsupported(narration, allowed_figures([RISK], [])) != []


def test_the_users_own_message_is_a_source_but_history_is_not():
    allowed = allowed_figures([], ["Can I afford an RM 1,299 laptop?"])
    assert unsupported("A RM 1,299 laptop needs a risk check first.", allowed) == []
    assert unsupported("Last time you said RM 5,000.", allowed) == ["5,000"]


def test_small_counts_need_no_source():
    assert unsupported("You have 2 plans and 3 bills.", set()) == []
    assert unsupported("You have 13 plans.", set()) == ["13"]


def test_a_figure_glued_to_rm_or_a_word_is_still_checked():
    assert unsupported("You can spend RM450 more.", set()) == ["450"]
    assert unsupported("Costs RM799.00 in total.", allowed_figures([{"x_sen": 79900}], [])) == []
