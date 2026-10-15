import pytest

from app.domain.categories import (
    BUILT_IN,
    MAX_NAME_LENGTH,
    build_listing,
    clean_name,
    locked_name,
)
from app.domain.categorize import BNPL, CATEGORY_KEYWORDS, DEFAULT_CATEGORY, REFUND, TRANSFER


def test_every_category_the_importer_can_guess_is_a_built_in_one():
    # If the guesser learns a new category and this list does not, the person could not even pick
    # what the importer picked for them.
    guessed = set(CATEGORY_KEYWORDS) | {DEFAULT_CATEGORY}

    assert guessed - {BNPL} <= set(BUILT_IN)


def test_the_engines_reserved_categories_are_built_in_and_locked():
    assert {REFUND, TRANSFER} <= set(BUILT_IN)
    assert locked_name(BNPL) == BNPL  # added by plans, never picked by hand


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Gym", "Gym"),
        ("  Boyfriend   Tax ", "Boyfriend Tax"),
        ("Drink/Dessert", "Drink/Dessert"),
        ("Self-Care", "Self-Care"),
        ("Kuih & Snacks", "Kuih & Snacks"),
        ("Zakat 2.5%", "Zakat 2.5%"),
    ],
)
def test_a_category_name_is_trimmed_and_its_spaces_collapsed(raw, clean):
    assert clean_name(raw) == clean


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "123", "--", None, 5, "a" * (MAX_NAME_LENGTH + 1), "Gym\nclass", "Gym\x00"],
)
def test_a_name_with_no_letter_or_that_is_too_long_or_has_control_characters_is_refused(raw):
    with pytest.raises(ValueError):
        clean_name(raw)


@pytest.mark.parametrize("raw", ["food", "FOOD", " bnpl ", "refund"])
def test_a_built_in_name_is_recognised_whatever_its_case(raw):
    assert locked_name(raw) is not None


def test_a_name_that_is_not_built_in_is_not_locked():
    assert locked_name("Gym") is None


def test_the_listing_starts_with_the_built_in_ones_then_the_persons_own_in_order():
    entries = build_listing(custom_names=["Zakat", "gym"], counts={})

    names = [e.name for e in entries]
    assert names[: len(BUILT_IN)] == list(BUILT_IN)
    assert names[len(BUILT_IN) :] == [BNPL, "gym", "Zakat"]


def test_built_in_entries_are_locked_and_the_persons_own_are_not():
    entries = {e.name: e for e in build_listing(["Gym"], {})}

    assert entries["Food"].builtin and entries["Food"].locked
    assert entries["Gym"].builtin is False and entries["Gym"].locked is False


def test_bnpl_is_listed_but_cannot_be_chosen_by_hand():
    entries = {e.name: e for e in build_listing([], {})}

    assert entries[BNPL].locked and entries[BNPL].assignable is False
    assert entries["Food"].assignable and entries[REFUND].assignable


def test_a_category_that_only_exists_on_transactions_is_still_the_persons_own():
    # Typed in their own spreadsheet and imported as written (D-42): never added by hand.
    entries = {e.name: e for e in build_listing([], {"Boyfriend Tax": 4, "Food": 10})}

    assert entries["Boyfriend Tax"].locked is False
    assert entries["Boyfriend Tax"].transaction_count == 4
    assert entries["Food"].transaction_count == 10


def test_a_category_added_by_hand_and_also_on_transactions_is_listed_once():
    entries = build_listing(["Gym"], {"Gym": 3})

    assert [e.name for e in entries].count("Gym") == 1
    assert {e.name: e.transaction_count for e in entries}["Gym"] == 3


def test_a_category_nobody_used_has_a_count_of_zero():
    assert {e.name: e.transaction_count for e in build_listing(["Gym"], {})}["Gym"] == 0


def test_reserved_categories_say_what_they_do():
    entries = {e.name: e for e in build_listing([], {})}

    assert entries[REFUND].note and entries[TRANSFER].note and entries[BNPL].note
    assert entries["Food"].note is None
