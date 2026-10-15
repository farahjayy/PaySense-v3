"""/api/categories: the categories a person can pick, and managing their own (ADR D-43)."""

import pytest

from app.domain.categories import BUILT_IN


def spend(api, headers, category, *, amount_sen=1000, **extra):
    body = {
        "date": "2026-06-10",
        "amount_sen": amount_sen,
        "type": "expense",
        "category": category,
        "description": "x",
    } | extra
    res = api.post("/api/transactions", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def listing(api, headers):
    res = api.get("/api/categories", headers=headers)
    assert res.status_code == 200, res.text
    return {c["name"]: c for c in res.json()["categories"]}


def add(api, headers, name):
    return api.post("/api/categories", json={"name": name}, headers=headers)


def rename(api, headers, name, new_name):
    return api.patch("/api/categories", json={"name": name, "new_name": new_name}, headers=headers)


def delete(api, headers, name, **params):
    return api.delete("/api/categories", params={"name": name, **params}, headers=headers)


def code(res):
    return res.json()["detail"]["code"]


def count_of(api, headers, category):
    return api.get(
        "/api/transactions",
        params={"category": category, "start": "2026-06-01", "end": "2026-06-30"},
        headers=headers,
    ).json()


# ------------------------------------------------------------------ list
def test_a_new_user_sees_the_built_in_categories_locked_and_unused(api, amir):
    entries = listing(api, amir)

    assert [n for n, c in entries.items() if c["builtin"]] == [*BUILT_IN, "BNPL"]
    assert all(c["locked"] and c["transaction_count"] == 0 for c in entries.values())
    assert entries["BNPL"]["assignable"] is False
    assert entries["Food"]["assignable"] is True
    assert entries["Refund"]["note"]


def test_the_list_counts_transactions_and_includes_categories_only_a_file_carried(api, amir):
    spend(api, amir, "Food")
    spend(api, amir, "Food")
    spend(api, amir, "Boyfriend Tax")

    entries = listing(api, amir)

    assert entries["Food"]["transaction_count"] == 2
    assert entries["Boyfriend Tax"] == {
        "name": "Boyfriend Tax",
        "builtin": False,
        "locked": False,
        "assignable": True,
        "note": None,
        "transaction_count": 1,
    }


# ------------------------------------------------------------------ add
def test_adding_a_category_makes_it_appear_unlocked_with_no_transactions(api, amir):
    res = add(api, amir, "  Gym   class ")

    assert res.status_code == 201
    assert res.json()["name"] == "Gym class" and res.json()["locked"] is False
    assert listing(api, amir)["Gym class"]["transaction_count"] == 0


@pytest.mark.parametrize("name", ["Gym", "gym", "GYM"])
def test_a_name_the_person_already_has_is_refused_in_any_case(api, amir, name):
    add(api, amir, "Gym")

    res = add(api, amir, name)

    assert res.status_code == 409 and code(res) == "category_exists"


@pytest.mark.parametrize("name", ["Food", "food", "Refund", "BNPL", "bnpl"])
def test_a_built_in_name_cannot_be_added(api, amir, name):
    res = add(api, amir, name)

    assert res.status_code == 409 and code(res) == "category_exists"


def test_a_name_a_file_already_brought_in_cannot_be_added_again(api, amir):
    spend(api, amir, "Boyfriend Tax")

    assert code(add(api, amir, "boyfriend tax")) == "category_exists"


@pytest.mark.parametrize("name", ["123", "--", "x" * 41, "Gym\u0000"])
def test_an_unusable_name_is_refused(api, amir, name):
    res = add(api, amir, name)

    assert res.status_code == 422


def test_a_blank_name_is_refused_with_the_envelope(api, amir):
    res = add(api, amir, "   ")

    assert res.status_code == 422 and code(res) == "validation_error"


# ------------------------------------------------------------------ rename
def test_renaming_a_category_moves_every_transaction_that_used_it(api, amir):
    add(api, amir, "Gym")
    spend(api, amir, "Gym")
    spend(api, amir, "Gym")
    spend(api, amir, "Food")

    res = rename(api, amir, "Gym", "Fitness")

    assert res.status_code == 200
    assert res.json()["moved"] == 2
    assert res.json()["category"]["name"] == "Fitness"
    entries = listing(api, amir)
    assert "Gym" not in entries
    assert entries["Fitness"]["transaction_count"] == 2
    assert entries["Food"]["transaction_count"] == 1
    assert len(count_of(api, amir, "Fitness")) == 2 and count_of(api, amir, "Gym") == []


def test_a_category_that_only_a_file_carried_can_be_renamed_and_then_stays(api, amir):
    tx = spend(api, amir, "Self Care")

    assert rename(api, amir, "Self Care", "Selfcare").status_code == 200
    api.delete(f"/api/transactions/{tx['id']}", headers=amir)

    assert "Selfcare" in listing(api, amir)  # the person chose this name; it is kept


def test_only_the_case_of_a_name_can_change(api, amir):
    add(api, amir, "gym")

    res = rename(api, amir, "gym", "Gym")

    assert (
        res.status_code == 200 and "Gym" in listing(api, amir) and "gym" not in listing(api, amir)
    )


@pytest.mark.parametrize("name", ["Food", "Refund", "Transfer", "BNPL", "Other"])
def test_a_built_in_category_cannot_be_renamed(api, amir, name):
    res = rename(api, amir, name, "Something else")

    assert res.status_code == 409 and code(res) == "category_locked"


def test_renaming_a_category_that_does_not_exist_is_a_404(api, amir):
    res = rename(api, amir, "Nope", "Something")

    assert res.status_code == 404 and code(res) == "category_not_found"


def test_renaming_into_a_name_that_is_taken_is_refused_and_moves_nothing(api, amir):
    add(api, amir, "Gym")
    add(api, amir, "Fitness")
    spend(api, amir, "Gym")

    res = rename(api, amir, "Gym", "fitness")

    assert res.status_code == 409 and code(res) == "category_exists"
    assert listing(api, amir)["Gym"]["transaction_count"] == 1


@pytest.mark.parametrize("new_name", ["Food", "food", "BNPL"])
def test_renaming_into_a_built_in_name_is_refused(api, amir, new_name):
    add(api, amir, "Gym")

    assert code(rename(api, amir, "Gym", new_name)) == "category_exists"


def test_renaming_to_an_unusable_name_is_refused(api, amir):
    add(api, amir, "Gym")

    assert rename(api, amir, "Gym", "123").status_code == 422


# ------------------------------------------------------------------ delete
def test_an_unused_category_can_be_deleted(api, amir):
    add(api, amir, "Gym")

    res = delete(api, amir, "Gym")

    assert res.status_code == 200 and res.json() == {"moved": 0}
    assert "Gym" not in listing(api, amir)


def test_a_used_category_needs_somewhere_to_move_its_transactions(api, amir):
    add(api, amir, "Gym")
    spend(api, amir, "Gym")

    res = delete(api, amir, "Gym")

    assert res.status_code == 409 and code(res) == "category_in_use"
    assert "Gym" in listing(api, amir)


def test_deleting_moves_its_transactions_where_asked(api, amir):
    add(api, amir, "Gym")
    spend(api, amir, "Gym")
    spend(api, amir, "Gym")

    res = delete(api, amir, "Gym", move_to="Other")

    assert res.status_code == 200 and res.json() == {"moved": 2}
    entries = listing(api, amir)
    assert "Gym" not in entries and entries["Other"]["transaction_count"] == 2


def test_two_of_the_persons_categories_can_be_merged_by_deleting_one_into_the_other(api, amir):
    spend(api, amir, "Self Care")
    spend(api, amir, "Self-Care")
    spend(api, amir, "Self-Care")

    assert delete(api, amir, "Self Care", move_to="Self-Care").json() == {"moved": 1}

    assert listing(api, amir)["Self-Care"]["transaction_count"] == 3


@pytest.mark.parametrize("target", ["Nope", "Gym", "BNPL", "bnpl"])
def test_a_move_target_must_exist_differ_and_be_pickable(api, amir, target):
    add(api, amir, "Gym")
    spend(api, amir, "Gym")

    res = delete(api, amir, "Gym", move_to=target)

    assert res.status_code == 422 and code(res) == "invalid_move_target"
    assert listing(api, amir)["Gym"]["transaction_count"] == 1


@pytest.mark.parametrize("name", ["Food", "Refund", "BNPL"])
def test_a_built_in_category_cannot_be_deleted(api, amir, name):
    res = delete(api, amir, name)

    assert res.status_code == 409 and code(res) == "category_locked"


def test_deleting_a_category_that_does_not_exist_is_a_404(api, amir):
    assert delete(api, amir, "Nope").status_code == 404


# ------------------------------------------------------------------ isolation and auth
def test_each_user_has_their_own_categories(api, amir, siti):
    add(api, amir, "Gym")
    spend(api, amir, "Gym")

    assert "Gym" not in listing(api, siti)
    assert add(api, siti, "Gym").status_code == 201  # not a duplicate of amir's


def test_one_user_cannot_rename_or_delete_anothers_category(api, amir, siti):
    add(api, amir, "Gym")
    spend(api, amir, "Gym")

    assert rename(api, siti, "Gym", "Mine").status_code == 404
    assert delete(api, siti, "Gym", move_to="Other").status_code == 404
    assert listing(api, amir)["Gym"]["transaction_count"] == 1


def test_a_rename_only_moves_the_callers_transactions(api, amir, siti):
    add(api, amir, "Gym")
    spend(api, amir, "Gym")
    spend(api, siti, "Gym")  # siti typed the same word on her own row

    rename(api, amir, "Gym", "Fitness")

    assert listing(api, siti)["Gym"]["transaction_count"] == 1
    assert len(count_of(api, siti, "Gym")) == 1


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [
        ("get", {}),
        ("post", {"json": {"name": "Gym"}}),
        ("patch", {"json": {"name": "Gym", "new_name": "Gym2"}}),
        ("delete", {"params": {"name": "Gym"}}),
    ],
)
def test_every_route_needs_a_login(api, method, kwargs):
    assert getattr(api, method)("/api/categories", **kwargs).status_code == 401


# ------------------------------------------------------------------ found in review
def test_a_rename_the_database_refuses_moves_no_transactions(api, amir, monkeypatch):
    # The name is written first, so a clash the database catches (a second tab, case rules that
    # differ) happens before any transaction has moved and there is nothing to undo.
    from app.api import categories as routes

    add(api, amir, "Gym")
    spend(api, amir, "Gym")

    def clash(*_args, **_kwargs):
        raise routes.categories.DuplicateCategory("taken")

    monkeypatch.setattr(routes.categories, "rename", clash)

    res = rename(api, amir, "Gym", "Fitness")

    assert res.status_code == 409 and code(res) == "category_exists"
    assert listing(api, amir)["Gym"]["transaction_count"] == 1


def test_a_rename_whose_move_fails_puts_the_name_back(api, amir, monkeypatch):
    from app.api import categories as routes

    add(api, amir, "Gym")
    spend(api, amir, "Gym")

    def broken(*_args, **_kwargs):
        raise RuntimeError("the connection dropped")

    monkeypatch.setattr(routes.transactions, "recategorise", broken)
    with pytest.raises(RuntimeError):
        rename(api, amir, "Gym", "Fitness")

    entries = listing(api, amir)
    assert "Fitness" not in entries
    assert entries["Gym"]["transaction_count"] == 1


def test_a_failed_rename_of_a_category_only_a_file_carried_leaves_no_new_name_behind(
    api, amir, monkeypatch
):
    from app.api import categories as routes

    spend(api, amir, "Self Care")

    def broken(*_args, **_kwargs):
        raise RuntimeError("the connection dropped")

    monkeypatch.setattr(routes.transactions, "recategorise", broken)
    with pytest.raises(RuntimeError):
        rename(api, amir, "Self Care", "Selfcare")

    entries = listing(api, amir)
    assert "Selfcare" not in entries
    assert entries["Self Care"]["transaction_count"] == 1


@pytest.mark.parametrize("target", ["Refund", "Transfer", "refund", "transfer"])
def test_transactions_cannot_be_moved_into_refund_or_transfer(api, amir, target):
    # Refund and Transfer change how a row counts (back out of spending; left out altogether), so
    # moving spending into them would silently change the month and the forecast.
    add(api, amir, "Gym")
    spend(api, amir, "Gym")

    res = delete(api, amir, "Gym", move_to=target)

    assert res.status_code == 422 and code(res) == "invalid_move_target"
    assert listing(api, amir)["Gym"]["transaction_count"] == 1


@pytest.mark.parametrize("name", ["Refund​", "Fo​od", "‮Gym", "Gym"])
def test_a_name_with_invisible_characters_is_refused(api, amir, name):
    assert add(api, amir, name).status_code == 422


def test_a_fullwidth_look_alike_of_a_built_in_name_is_the_built_in_name(api, amir):
    # NFKC folds "Ｆｏｏｄ" to "Food", which is built in.
    assert add(api, amir, "Ｆｏｏｄ").status_code == 409


def test_a_hand_typed_built_in_name_is_stored_spelled_the_apps_way(api, amir):
    # "food" and "transfer" would otherwise be categories of the person's own that cannot be
    # renamed, deleted or merged, and "transfer" would not be treated as a transfer.
    spend(api, amir, "food")
    spend(api, amir, "TRANSFER")

    entries = listing(api, amir)

    assert entries["Food"]["transaction_count"] == 1
    assert entries["Transfer"]["transaction_count"] == 1
    assert "food" not in entries and "TRANSFER" not in entries


def test_editing_a_transaction_to_a_built_in_name_in_other_case_is_stored_the_apps_way(api, amir):
    tx = spend(api, amir, "Gym")
    api.patch(f"/api/transactions/{tx['id']}", json={"category": "refund"}, headers=amir)

    assert listing(api, amir)["Refund"]["transaction_count"] == 1


def test_the_schema_advertises_the_real_name_limit(api):
    schema = api.get("/openapi.json").json()["components"]["schemas"]

    assert schema["CategoryIn"]["properties"]["name"]["maxLength"] == 40
    assert schema["CategoryRenameIn"]["properties"]["new_name"]["maxLength"] == 40


def test_changing_categories_too_quickly_is_slowed_down(api, amir):
    codes = [add(api, amir, f"Group {chr(97 + i)}").status_code for i in range(25)]

    assert codes[0] == 201
    assert 429 in codes
