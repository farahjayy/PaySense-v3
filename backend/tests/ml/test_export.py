import csv
import hashlib
import json
from datetime import date, timedelta

import pytest

from ml.datagen.export import (
    COHORT_COLUMNS,
    COHORT_FILE,
    MANIFEST_FILE,
    PROFILES_FILE,
    export_synthetic,
    main,
    weekly_series,
)
from ml.datagen.params import load_params
from ml.datagen.profile import generate_profile

PARAMS = load_params()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("synthetic")
    manifest = export_synthetic(PARAMS, seed=9, count=12, out_dir=out)
    return out, manifest


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_one_profile_line_is_written_per_student_in_index_order(run):
    out, _ = run
    profiles = jsonl(out / PROFILES_FILE)

    assert [p["index"] for p in profiles] == list(range(12))


def test_a_profile_line_carries_everything_engine_two_needs(run):
    out, _ = run
    profile = jsonl(out / PROFILES_FILE)[0]

    for key in (
        "persona",
        "as_of",
        "expected_monthly_income_sen",
        "transactions",
        "plans",
        "limits",
        "actual_limits",
        "purchase",
        "recurring_truth",
    ):
        assert key in profile, key
    assert date.fromisoformat(profile["as_of"])
    first = profile["transactions"][0]
    assert date.fromisoformat(first["date"]) and isinstance(first["amount_sen"], int)
    assert profile["purchase"]["proposal"]["instalments"][0]["due_date"]


def test_the_manifest_matches_what_was_written(run):
    out, manifest = run

    assert manifest == json.loads((out / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert manifest["seed"] == 9 and manifest["profiles"] == 12
    assert manifest["params_hash"] == PARAMS.hash()
    assert sum(manifest["persona_counts"].values()) == 12
    assert manifest["files"][PROFILES_FILE]["sha256"] == sha256(out / PROFILES_FILE)
    assert manifest["files"][COHORT_FILE]["sha256"] == sha256(out / COHORT_FILE)
    assert manifest["files"][PROFILES_FILE]["rows"] == 12
    assert "python" in manifest["versions"] and "numpy" in manifest["versions"]


def test_the_manifest_has_no_timestamp_so_it_can_be_committed(run):
    _, manifest = run

    assert "created" not in json.dumps(manifest).lower()


def test_exporting_twice_gives_byte_identical_files(run, tmp_path):
    out, manifest = run
    again = export_synthetic(PARAMS, seed=9, count=12, out_dir=tmp_path)

    assert again == manifest
    for name in (PROFILES_FILE, COHORT_FILE):
        assert sha256(out / name) == sha256(tmp_path / name)


def test_a_smaller_run_is_a_prefix_of_a_larger_one(run, tmp_path):
    out, _ = run
    export_synthetic(PARAMS, seed=9, count=5, out_dir=tmp_path)

    small = (tmp_path / PROFILES_FILE).read_text(encoding="utf-8").splitlines()
    large = (out / PROFILES_FILE).read_text(encoding="utf-8").splitlines()
    assert large[:5] == small


def test_the_cohort_file_has_one_row_per_profile_week(run):
    out, _ = run
    with (out / COHORT_FILE).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert tuple(reader.fieldnames) == COHORT_COLUMNS
    assert {int(r["profile_index"]) for r in rows} == set(range(12))
    per_profile = {}
    for r in rows:
        per_profile.setdefault(r["profile_index"], []).append(date.fromisoformat(r["week_start"]))
    for weeks in per_profile.values():
        assert weeks == sorted(weeks) and len(weeks) >= 70  # 18 months of complete weeks
        assert all(w.weekday() == 0 for w in weeks)
        assert all(b - a == timedelta(days=7) for a, b in zip(weeks, weeks[1:], strict=False))


def test_weekly_series_covers_only_complete_monday_to_sunday_weeks():
    profile = generate_profile(PARAMS, 9, 0)
    series = weekly_series(profile)

    assert series[0].week_start >= profile.start
    assert series[0].week_start.weekday() == 0
    assert series[-1].week_start + timedelta(days=6) <= profile.as_of


def test_weekly_series_adds_up_to_the_generators_own_totals_over_those_weeks():
    profile = generate_profile(PARAMS, 9, 3, persona="irregular_income")
    series = weekly_series(profile)
    lo, hi = series[0].week_start, series[-1].week_start + timedelta(days=6)

    income = sum(t.amount_sen for t in profile.income_events if lo <= t.date <= hi)
    spend = sum(
        t.amount_sen
        for t in profile.discretionary_events
        if lo <= t.date <= hi and t.type == "expense" and t.category not in ("Transfer",)
    )
    refunds = sum(
        t.amount_sen
        for t in profile.discretionary_events
        if lo <= t.date <= hi and t.category == "Refund"
    )
    assert sum(w.income_sen for w in series) == income
    # a refund larger than its own week's spending is floored at zero, so the total sits between
    # "spend net of every refund" and "spend ignoring refunds"
    assert spend - refunds <= sum(w.discretionary_sen for w in series) <= spend
    assert all(w.discretionary_sen >= 0 for w in series)


def test_the_command_line_entry_point_writes_a_run(tmp_path):
    main(["--profiles", "3", "--seed", "4", "--out", str(tmp_path)])

    assert len(jsonl(tmp_path / PROFILES_FILE)) == 3
    assert json.loads((tmp_path / MANIFEST_FILE).read_text(encoding="utf-8"))["seed"] == 4


def test_a_non_positive_profile_count_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="count"):
        export_synthetic(PARAMS, seed=1, count=0, out_dir=tmp_path)
