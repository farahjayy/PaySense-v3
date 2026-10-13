"""UAT analysis: SUS scoring, interval, validation, switch table, report."""

from pathlib import Path

import pytest

from ml.uat.analyse import build_report, main, safe_cell
from ml.uat.load import (
    UatDataError,
    load_choices,
    load_clarity,
    load_sus,
    load_vignettes,
)
from ml.uat.sus import mean_interval, sus_score
from ml.uat.switches import switch_table

ROOT = Path(__file__).resolve().parents[4]
VIGNETTES = ROOT / "uat" / "vignettes.yaml"
EXAMPLE = ROOT / "uat" / "data" / "example"
TEMPLATES = ROOT / "uat" / "templates"


class TestSusScore:
    def test_best_possible_answers_score_100(self):
        assert sus_score([5, 1, 5, 1, 5, 1, 5, 1, 5, 1]) == 100

    def test_worst_possible_answers_score_0(self):
        assert sus_score([1, 5, 1, 5, 1, 5, 1, 5, 1, 5]) == 0

    def test_all_neutral_scores_50(self):
        assert sus_score([3] * 10) == 50

    def test_hand_computed_mixed_case(self):
        # odd items: 4,3,5,2,4 -> 3+2+4+1+3 = 13; even items: 2,1,3,2,2 -> 3+4+2+3+3 = 15
        assert sus_score([4, 2, 3, 1, 5, 3, 2, 2, 4, 2]) == (13 + 15) * 2.5

    @pytest.mark.parametrize("bad", [[3] * 9, [3] * 11, [0] + [3] * 9, [6] + [3] * 9])
    def test_wrong_length_or_out_of_range_is_rejected(self, bad):
        with pytest.raises(ValueError):
            sus_score(bad)


class TestInterval:
    def test_matches_a_hand_computed_t_interval(self):
        out = mean_interval([60, 70, 80])
        assert out.n == 3
        assert out.mean == pytest.approx(70)
        # t(0.975, df=2) = 4.302653; sd = 10; half-width = 4.302653 * 10 / sqrt(3)
        assert out.low == pytest.approx(70 - 24.8414, abs=1e-3)
        assert out.high == pytest.approx(70 + 24.8414, abs=1e-3)

    def test_one_tester_has_a_mean_but_no_interval(self):
        out = mean_interval([72.5])
        assert (out.mean, out.low, out.high) == (72.5, None, None)

    def test_no_values_is_an_error(self):
        with pytest.raises(ValueError):
            mean_interval([])


class TestVignetteFile:
    def test_every_vignette_has_distinct_ranked_options_and_a_stated_reason(self):
        import yaml

        raw = yaml.safe_load(VIGNETTES.read_text(encoding="utf-8"))
        assert raw["ordering_note"].strip()
        vignettes = load_vignettes(VIGNETTES)
        assert len(vignettes) >= 3
        for v in vignettes.values():
            ranks = [o.risk_rank for o in v.options]
            assert len(v.options) >= 4
            assert len(set(ranks)) == len(ranks)
            assert min(ranks) == 0


class TestTemplates:
    def test_blank_templates_have_the_headers_the_loader_expects(self):
        # the header check passes, so the only complaint is that nobody has answered yet
        vignettes = load_vignettes(VIGNETTES)
        for load in (load_sus, load_clarity):
            with pytest.raises(UatDataError, match="no responses"):
                load(TEMPLATES / ("sus.csv" if load is load_sus else "clarity.csv"))
        with pytest.raises(UatDataError, match="no responses"):
            load_choices(TEMPLATES / "vignettes.csv", vignettes)


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


class TestValidation:
    def test_out_of_range_answer_names_the_row_and_column(self, tmp_path):
        f = write(tmp_path / "clarity.csv", "participant,c1,c2,c3,c4\nP01,5,4,4,4\nP02,5,9,4,4\n")
        with pytest.raises(UatDataError, match=r"row 3: c2 must be 1-5"):
            load_clarity(f)

    def test_duplicate_participant_is_an_error_not_a_smaller_sample(self, tmp_path):
        f = write(tmp_path / "clarity.csv", "participant,c1,c2,c3,c4\nP01,5,4,4,4\nP01,3,3,3,3\n")
        with pytest.raises(UatDataError, match="appears twice"):
            load_clarity(f)

    def test_wrong_header_is_rejected(self, tmp_path):
        f = write(tmp_path / "sus.csv", "who,a,b\nP01,1,2\n")
        with pytest.raises(UatDataError, match="header must be"):
            load_sus(f)

    def test_unknown_vignette_option_and_phase_are_rejected(self, tmp_path):
        vignettes = load_vignettes(VIGNETTES)
        head = "participant,vignette,phase,option,confidence\n"
        for row, message in [
            ("P01,V9,pre,A,3", "unknown vignette"),
            ("P01,V1,pre,Z,3", "unknown option"),
            ("P01,V1,mid,A,3", "phase must be"),
            ("P01,V1,pre,A,7", "confidence must be"),
        ]:
            with pytest.raises(UatDataError, match=message):
                load_choices(write(tmp_path / "v.csv", head + row + "\n"), vignettes)

    def test_a_repeated_answer_is_rejected(self, tmp_path):
        vignettes = load_vignettes(VIGNETTES)
        f = write(
            tmp_path / "v.csv",
            "participant,vignette,phase,option,confidence\nP01,V1,pre,A,3\nP01,V1,pre,B,3\n",
        )
        with pytest.raises(UatDataError, match="repeated"):
            load_choices(f, vignettes)


class TestSwitchTable:
    def build(self, tmp_path, rows: str):
        vignettes = load_vignettes(VIGNETTES)
        f = write(tmp_path / "v.csv", "participant,vignette,phase,option,confidence\n" + rows)
        choices, _ = load_choices(f, vignettes)
        return {r.vignette: r for r in switch_table(choices, vignettes)}

    def test_direction_follows_the_risk_ranking(self, tmp_path):
        table = self.build(
            tmp_path,
            "P01,V1,pre,A,3\nP01,V1,post,C,4\n"  # 4 -> 2: safer
            "P02,V1,pre,A,3\nP02,V1,post,A,3\n"  # same
            "P03,V1,pre,D,3\nP03,V1,post,B,2\n",  # 1 -> 3: riskier
        )
        v1 = table["V1"]
        assert (v1.n, v1.same, v1.safer, v1.riskier, v1.switched) == (3, 1, 1, 1, 2)
        assert ("A", "C", 1) in v1.transitions
        assert v1.confidence_before == pytest.approx(3.0)
        assert v1.confidence_after == pytest.approx(3.0)

    def test_a_tester_with_only_one_phase_is_not_counted(self, tmp_path):
        table = self.build(tmp_path, "P01,V2,pre,A,3\n")
        assert table["V2"].n == 0
        assert table["V2"].confidence_before is None


class TestReport:
    def test_example_data_is_labelled_invented_and_reports_mean_and_ci(self):
        report, scores, table = build_report(EXAMPLE, VIGNETTES)
        assert report.startswith("# UAT analysis")
        assert "Invented example data" in report
        assert len(scores) == 6
        assert "95% CI" in report
        assert "Decisions before and after the risk check" in report
        assert all(r.n == 6 for r in table)

    def test_main_writes_the_report_and_escaped_csv_tables(self, tmp_path, capsys):
        out = tmp_path / "sub" / "report.md"
        code = main(["--data", str(EXAMPLE), "--vignettes", str(VIGNETTES), "--out", str(out)])
        assert code == 0
        assert out.read_text(encoding="utf-8").startswith("# UAT analysis")
        assert (out.parent / "report_sus_scores.csv").exists()
        assert (out.parent / "report_switches.csv").exists()
        assert "Mean SUS" in capsys.readouterr().out

    def test_main_reports_a_bad_data_folder_without_a_traceback(self, tmp_path, capsys):
        assert main(["--data", str(tmp_path), "--vignettes", str(VIGNETTES)]) == 2
        assert "Cannot analyse" in capsys.readouterr().err

    @pytest.mark.parametrize("value", ["=1+1", "+1", "-2", "@x", "\tx"])
    def test_cells_that_look_like_formulas_are_neutralised(self, value):
        assert safe_cell(value).startswith("'")

    def test_ordinary_cells_are_unchanged(self):
        assert safe_cell("P01") == "P01"
        assert safe_cell(72.5) == "72.5"


class TestLoaderRobustness:
    def test_a_row_with_too_many_columns_is_an_error_that_names_it(self, tmp_path):
        path = tmp_path / "sus.csv"
        path.write_text(
            "participant,s1,s2,s3,s4,s5,s6,s7,s8,s9,s10\nP1,3,3,3,3,3,3,3,3,3,3,9\n",
            encoding="utf-8",
        )
        with pytest.raises(UatDataError, match="too many columns"):
            load_sus(path)

    @pytest.mark.parametrize("loader", [load_sus, load_clarity])
    def test_a_header_only_file_is_an_error_not_an_empty_sample(self, tmp_path, loader):
        copy = tmp_path / "x.csv"
        template = TEMPLATES / ("sus.csv" if loader is load_sus else "clarity.csv")
        copy.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        with pytest.raises(UatDataError, match="no responses"):
            loader(copy)

    def test_main_on_the_blank_templates_says_so_without_a_traceback(self, tmp_path, capsys):
        assert main(["--data", str(TEMPLATES), "--vignettes", str(VIGNETTES)]) == 2
        assert "no responses" in capsys.readouterr().err

    def test_a_vignette_file_with_a_missing_key_or_repeated_id_is_a_data_error(self, tmp_path):
        broken = tmp_path / "v.yaml"
        broken.write_text("vignettes:\n  - id: V1\n    title: T\n", encoding="utf-8")
        with pytest.raises(UatDataError, match="options"):
            load_vignettes(broken)
        twice = tmp_path / "w.yaml"
        item = "  - id: V1\n    title: T\n    options:\n      - {id: a, text: A, risk_rank: 1}\n"
        twice.write_text("vignettes:\n" + item + item, encoding="utf-8")
        with pytest.raises(UatDataError, match="twice"):
            load_vignettes(twice)


class TestCsvFormulaGuard:
    def test_written_csv_neutralises_formulas_and_leaves_none_empty(self, tmp_path):
        from ml.uat.analyse import write_csv

        path = tmp_path / "out.csv"
        write_csv(path, ["name", "value"], [("=cmd", None), ("fine", 3)])
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[1] == "'=cmd,"
        assert lines[2] == "fine,3"


class TestSusInputs:
    def test_a_fractional_or_boolean_answer_is_refused(self):
        for bad in ([3.5] * 10, [True] * 10):
            with pytest.raises(ValueError, match="whole numbers"):
                sus_score(bad)

    def test_an_interval_level_outside_zero_to_one_is_refused(self):
        for level in (0, 1, 1.5):
            with pytest.raises(ValueError, match="level"):
                mean_interval([60.0, 70.0], level=level)
