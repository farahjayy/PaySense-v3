"""WP9: the evidence collector reports how each check ended, never a pass it did not see."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "collect_test_evidence.py"
spec = importlib.util.spec_from_file_location("collect_test_evidence", SCRIPT)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def test_result_lines_pick_out_counts_coverage_and_failures():
    output = "....\nTOTAL   5000   400   92%\n2008 passed, 25 deselected in 108.30s\n"
    assert collector.result_lines(output) == [
        "TOTAL   5000   400   92%",
        "2008 passed, 25 deselected in 108.30s",
    ]
    assert collector.result_lines("1 failed, 3 passed in 2s") == ["1 failed, 3 passed in 2s"]


def test_a_check_that_cannot_run_is_recorded_with_its_exit_code(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "OUT", tmp_path)
    monkeypatch.setattr(collector, "ROOT", tmp_path)
    (tmp_path / "x").mkdir()
    row = collector.run_check("missing", "x", ["definitely-not-a-command-xyz"])
    assert row["code"] == -1
    assert "could not run" in (tmp_path / "missing.txt").read_text(encoding="utf-8")
    assert "| missing |" in collector.render([row])
