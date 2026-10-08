import pytest

from app.domain.categorize import BNPL, REFUND, TRANSFER, guess_category, guess_type


# ------------------------------------------------------------------ ported from v1
def test_allowance_from_parents_is_not_rent():
    # Regression: substring matching used to find "rent" inside "parents".
    assert guess_category("Monthly Allowance from Parents") == "Allowance"


def test_prefix_boundary_still_matches_derived_words():
    assert guess_category("Room rental payment") == "Rent"
    assert guess_category("Printing service") == "Education"


def test_common_malaysian_merchants():
    assert guess_category("GrabFood Nasi Lemak") == "Food"
    assert guess_category("TNG eWallet Reload Toll") == "Transport"
    assert guess_category("Shopee - Phone Case") == "Shopping"
    assert guess_category("Unifi Mobile Bill") == "Bills"
    assert guess_category("Something Unrecognisable") == "Other"


def test_guess_type_sign_wins_over_keywords():
    assert guess_type("Salary credited", -1) == "expense"
    assert guess_type("Random purchase", 1) == "income"
    assert guess_type("Monthly salary", 0) == "income"
    assert guess_type("Mamak dinner", 0) == "expense"


# ------------------------------------------------------------------ v2: reserved categories
def test_reserved_category_names_are_stable():
    assert (REFUND, TRANSFER, BNPL) == ("Refund", "Transfer", "BNPL")


@pytest.mark.parametrize(
    "description",
    ["Shopee refund order 123", "GRAB REFUND", "Payment reversal", "Cashback Touch n Go"],
)
def test_refunds_win_over_the_merchant_they_came_from(description):
    assert guess_category(description) == REFUND


@pytest.mark.parametrize(
    "description",
    ["Transfer to own account", "TNG eWallet top up", "Topup ShopeePay", "Transfer to savings"],
)
def test_explicit_own_account_moves_are_transfers(description):
    assert guess_category(description) == TRANSFER


def test_a_bare_incoming_transfer_is_not_assumed_to_be_an_own_account_move():
    # Bank statements label a parent's allowance as "transfer in"; it is income, not a transfer.
    assert guess_category("DuitNow transfer in from Ahmad") != TRANSFER
    assert guess_type("DuitNow transfer in", 0) == "income"


def test_bnpl_category_is_never_guessed_from_text():
    assert guess_category("BNPL instalment") != BNPL
