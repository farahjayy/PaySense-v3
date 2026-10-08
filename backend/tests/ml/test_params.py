import pytest

from ml.datagen.params import (
    DEFAULT_PARAMS_PATH,
    DEFAULT_SOURCES_PATH,
    ParamError,
    load_params,
    parse_params,
    source_keys,
)

SOURCES = {"tok_cheah_2024", "ccob_repayment_2024"}


def cited(value=1, **extra):
    return {"value": value, "unit": "sen", "source": "tok_cheah_2024"} | extra


def assumed(value=1, **extra):
    return {"value": value, "unit": "sen", "assumed": True, "why": "no published figure"} | extra


# ------------------------------------------------------------------ the provenance rule
def test_a_leaf_with_a_source_or_an_assumption_is_accepted():
    params = parse_params({"a": {"x": cited(5), "y": assumed(7)}}, SOURCES)

    assert params["a.x"] == 5 and params["a.y"] == 7
    assert [p.path for p in params.cited()] == ["a.x"]
    assert [p.path for p in params.assumed()] == ["a.y"]


@pytest.mark.parametrize(
    ("leaf", "message"),
    [
        ({"value": 1, "unit": "sen"}, "source.*assumed"),  # neither
        (cited(assumed=True, why="both"), "both"),
        ({"value": 1, "unit": "sen", "assumed": True}, "why"),  # assumed without a reason
        ({"value": 1, "unit": "sen", "assumed": True, "why": "  "}, "why"),
        ({"value": 1, "unit": "sen", "source": "made_up_paper"}, "made_up_paper"),
        ({"value": 1, "unit": "sen", "source": "not_available"}, "not_available"),
        ({"value": 1, "source": "tok_cheah_2024"}, "unit"),
    ],
)
def test_a_leaf_without_honest_provenance_is_rejected(leaf, message):
    with pytest.raises(ParamError, match=message):
        parse_params({"a": {"x": leaf}}, SOURCES)


def test_the_error_names_the_offending_parameter():
    with pytest.raises(ParamError, match=r"income\.allowance"):
        parse_params({"income": {"allowance": {"value": 1, "unit": "sen"}}}, SOURCES)


def test_assumed_false_with_no_source_is_still_rejected():
    with pytest.raises(ParamError):
        parse_params({"a": {"x": {"value": 1, "unit": "sen", "assumed": False}}}, SOURCES)


# ------------------------------------------------------------------ access and the hash
def test_nested_sections_are_addressed_by_dotted_path():
    params = parse_params({"a": {"b": {"c": cited(3)}}, "z": assumed(9)}, SOURCES)

    assert params["a.b.c"] == 3
    assert params["z"] == 9
    assert params.param("a.b.c").unit == "sen"
    with pytest.raises(KeyError, match="a.missing"):
        params["a.missing"]


def test_the_hash_is_stable_and_changes_with_any_value_or_provenance():
    base = {"a": {"x": cited(5)}}
    first = parse_params(base, SOURCES).hash()

    assert parse_params({"a": {"x": cited(5)}}, SOURCES).hash() == first
    assert parse_params({"a": {"x": cited(6)}}, SOURCES).hash() != first
    assert parse_params({"a": {"x": assumed(5)}}, SOURCES).hash() != first


def test_the_hash_does_not_depend_on_key_order():
    one = parse_params({"a": {"x": cited(1), "y": cited(2)}}, SOURCES)
    two = parse_params({"a": {"y": cited(2), "x": cited(1)}}, SOURCES)

    assert one.hash() == two.hash()


# ------------------------------------------------------------------ the real files
def test_the_source_registry_lists_every_documented_source():
    keys = source_keys(DEFAULT_SOURCES_PATH)

    assert {"ptptn_loan_table", "tok_cheah_2024", "dosm_hes_2022", "ccob_repayment_2024"} <= keys
    assert "not_available" in keys  # present as a heading, but never citable (tested above)


def test_the_real_parameter_file_loads_and_every_parameter_has_provenance():
    params = load_params(DEFAULT_PARAMS_PATH, DEFAULT_SOURCES_PATH)

    assert len(params.all()) > 20
    for p in params.all():
        assert p.assumed != (p.source is not None), p.path  # exactly one of the two
        if p.assumed:
            assert p.why and p.why.strip(), p.path


def test_the_real_file_cites_only_what_the_sources_actually_support():
    params = load_params(DEFAULT_PARAMS_PATH, DEFAULT_SOURCES_PATH)

    assert params.param("repayment.on_time_share").source == "ccob_repayment_2024"
    assert params.param("repayment.on_time_share").value == 0.88
    assert params.param("income.ptptn_annual_sen").source == "ptptn_loan_table"
    # The PTPTN page gives no disbursement schedule, so that must be an assumption.
    assert params.param("income.ptptn_disbursements_per_year").assumed is True
    # Nobody published how many students use BNPL: assumed, not cited.
    assert params.param("bnpl.ownership_probability.budget_conscious").assumed is True


def test_the_assumed_list_is_printable_and_non_empty():
    params = load_params(DEFAULT_PARAMS_PATH, DEFAULT_SOURCES_PATH)

    text = params.describe_assumptions()

    assert params.assumed()
    assert all(p.path in text for p in params.assumed())
