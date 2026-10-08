import csv
import hashlib

import pytest

from ml.datagen.params import load_params
from ml.datagen.report import build_report

PARAMS = load_params()
SEED, COUNT = 17, 150


@pytest.fixture(scope="module")
def report_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("report")
    build_report(PARAMS, SEED, COUNT, out)
    return out


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_report_writes_readme_tables_and_figures(report_dir):
    assert (report_dir / "README.md").is_file()
    assert (report_dir / "tables" / "parameters.csv").is_file()
    assert (report_dir / "tables" / "moments.csv").is_file()
    figures = sorted(p.name for p in (report_dir / "figures").glob("*.png"))
    assert len(figures) >= 3


def test_every_parameter_is_listed_with_its_provenance(report_dir):
    rows = {r["path"]: r for r in read_csv(report_dir / "tables" / "parameters.csv")}

    assert set(rows) == {p.path for p in PARAMS.all()}
    for param in PARAMS.cited():
        assert rows[param.path]["provenance"] == f"cited: {param.source}"
    for param in PARAMS.assumed():
        assert rows[param.path]["provenance"] == "assumed"
        assert rows[param.path]["why"]


def test_every_cited_target_appears_in_the_moments_table(report_dir):
    paths = {r["param"] for r in read_csv(report_dir / "tables" / "moments.csv")}

    for param in PARAMS.cited():
        assert param.path in paths, param.path


def test_the_readme_names_every_assumed_parameter(report_dir):
    readme = (report_dir / "README.md").read_text(encoding="utf-8")

    for param in PARAMS.assumed():
        assert f"`{param.path}`" in readme, param.path


def test_the_readme_states_the_limitations_and_how_to_regenerate_it(report_dir):
    readme = (report_dir / "README.md").read_text(encoding="utf-8")

    assert "## Limitations" in readme
    assert "circular" in readme.lower()
    assert "no real students" in readme.lower()
    assert "python -m ml.datagen.report" in readme
    assert f"seed {SEED}" in readme and f"{COUNT} profiles" in readme
    assert PARAMS.hash() in readme


def test_measured_values_are_reported_next_to_their_targets_even_when_they_miss(report_dir):
    rows = read_csv(report_dir / "tables" / "moments.csv")
    targeted = [r for r in rows if r["target"] and r["measured"]]

    assert len(targeted) >= 5
    for r in targeted:
        assert r["status"] in {"within tolerance", "outside tolerance"}, r


def test_the_repayment_shares_are_compared_per_account_holder(report_dir):
    rows = {r["param"]: r for r in read_csv(report_dir / "tables" / "moments.csv")}

    on_time = float(rows["repayment.on_time_share"]["measured"])
    late = float(rows["repayment.late_but_paid_share"]["measured"])
    assert on_time == pytest.approx(0.88, abs=0.08)
    assert late == pytest.approx(0.12, abs=0.08)
    assert "holders" in rows["repayment.on_time_share"]["note"]


def test_wiring_checks_are_labelled_as_such(report_dir):
    rows = {r["param"]: r for r in read_csv(report_dir / "tables" / "moments.csv")}

    for param in ("bnpl.instalment_options.atome", "bnpl.limit_cap_sen.spaylater"):
        assert rows[param]["kind"] == "cited (wiring check)"
    assert rows["repayment.on_time_share"]["kind"] == "cited"


def test_regenerating_gives_byte_identical_output(report_dir, tmp_path):
    build_report(PARAMS, SEED, COUNT, tmp_path)

    names = ["README.md", "tables/parameters.csv", "tables/moments.csv"]
    names += [f"figures/{p.name}" for p in sorted((report_dir / "figures").glob("*.png"))]
    for name in names:
        assert digest(report_dir / name) == digest(tmp_path / name), name


def test_a_non_positive_profile_count_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="count"):
        build_report(PARAMS, SEED, 0, tmp_path)


def test_no_cited_parameter_is_left_unmeasured_without_saying_so(report_dir):
    rows = {r["param"]: r for r in read_csv(report_dir / "tables" / "moments.csv")}

    for param in PARAMS.cited():
        assert rows[param.path]["status"] != "not measured", param.path
