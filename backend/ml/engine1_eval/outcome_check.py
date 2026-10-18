"""Score the served P(shortfall) against what really happened (evaluation only):

    cd backend && uv run python -m ml.engine1_eval.outcome_check [--synthetic <csv>]

Every other Engine 1 figure measures the forecast (MASE) or the band (coverage of a 13-week total).
This one measures the number the product shows. For development students only, each weekly
ledger is cut 13 weeks (and, separately, 26 weeks) before its end. At the cut the script builds
what serving builds (`service.prepare_ledger` and `forecast_prepared`): the user's own error
record, widened by the served band table, the served LSTM's forecast and the same 1,000-path
Monte Carlo (`simulate.simulate`), and reads P(shortfall) for the next 13 weeks: the share of
paths whose running margin, from RM0 at the start of the cut's month plus the month so far, is
below RM0 at any month-end. The REALISED outcome is the same `simulate` call on the held-back
weeks with no error draws and one path, so both sides use one definition.

Benchmarks: a constant (the realised rate of the scored students at that cut, the best any
constant can do on them) and the same simulation driven by MA13 instead of the LSTM. History
length is varied by starting the ledger later (one case per bucket of 17-25, 26-38, 39-51 and
52+ weeks); the realised outcome does not depend on it.

It fits, chooses and changes nothing that is served. Writes `reports/engine1/outcome_check.md`
and `reports/engine1/tables/outcome_check.csv`.
"""

import argparse
import csv
import time
import zlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from app.engines.forecasting.bands import inflation_for
from app.engines.forecasting.errors import widen
from app.engines.forecasting.flows import known_flows
from app.engines.forecasting.series import WeeklySeries
from app.engines.forecasting.service import MIN_SERIES_WEEKS, error_record
from app.engines.forecasting.serving import served_forecaster
from app.engines.forecasting.simulate import (
    CAUTION_BELOW,
    DAYS_PER_WEEK,
    DEFAULT_PATHS,
    SAFE_BELOW,
    Forecaster,
    band,
    simulate,
)
from ml.engine1_eval.band_calibration import (
    BUCKETS,
    COHORT,
    DEV_PROFILES,
    EVAL_POOL,
    SEED,
    bucket_of,
    dev_profiles,
)
from ml.engine1_eval.band_calibration import test_profiles as engine1_test_profiles
from ml.engine1_eval.band_fresh_check import FRESH_PROFILES, fresh_profiles
from ml.engine1_eval.loaders.synthetic import DEFAULT_PATH, load_synthetic
from ml.engine2_train.data import LOCKBOX_EVERY

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "reports" / "engine1" / "outcome_check.md"
TABLE = ROOT / "reports" / "engine1" / "tables" / "outcome_check.csv"
OUTCOME_PROFILES = 2000
CUTS = (13, 26)  # weeks before the end of the ledger
HORIZON = 13  # weeks held back and scored
PATHS = DEFAULT_PATHS
EPS = 1 / (2 * PATHS)  # log loss clips P to half a simulated path from 0 and 1
BINS = 10
BOOTSTRAP_DRAWS = 1000
METHODS = ("lstm", "ma13")
LABELS = {"lstm": "served LSTM", "ma13": "MA13 (benchmark)", "constant": "constant (benchmark)"}
BUCKET_RANGES = tuple(
    (low, BUCKETS[i + 1] - 1 if i + 1 < len(BUCKETS) else None) for i, low in enumerate(BUCKETS)
)
BANDS = ("Safe", "Caution", "At Risk")


# --- which students and which cases ---------------------------------------------------------------


def outcome_profiles(count: int = OUTCOME_PROFILES, seed: int = SEED) -> list[int]:
    """A seeded draw of development students that no other Engine 1 check has used: cohort
    indices 4,000-9,999 outside Engine 2's lockbox, minus the band table's 300 fitting students
    and the 300 fresh-check students. The 60 Engine 1 test students (drawn from 0-3,999) are
    removed as well, in case that draw ever changes."""
    used = (
        set(dev_profiles(DEV_PROFILES, seed))
        | set(fresh_profiles(FRESH_PROFILES, seed))
        | set(engine1_test_profiles(seed))
    )
    pool = [i for i in range(EVAL_POOL, COHORT) if i % LOCKBOX_EVERY != 0 and i not in used]
    rng = np.random.default_rng(seed + 5)
    return sorted(int(i) for i in rng.choice(pool, size=count, replace=False))


def history_lengths(profile: int, cut: int, available: int, seed: int = SEED) -> list[int]:
    """One history length per bucket: seeded inside each bounded bucket, and the whole history
    before the cut for the open last bucket (when there is enough of it)."""
    rng = np.random.default_rng([seed, profile, cut])
    lengths = []
    for low, high in BUCKET_RANGES:
        if high is None:
            if available >= low:
                lengths.append(available)
        elif available >= low:
            lengths.append(int(rng.integers(low, min(high, available) + 1)))
    return lengths


def case_seed(profile: int, cut: int, weeks: int) -> int:
    """Deterministic per case, like serving's per-user, per-day seed; shared by both methods."""
    return zlib.crc32(f"{profile}:{cut}:{weeks}".encode())


# --- what serving builds at the cut ---------------------------------------------------------------


def _forecast_from(series: WeeklySeries) -> date:
    return series.start + timedelta(days=DAYS_PER_WEEK * series.weeks)


def month_to_date_sen(series: WeeklySeries, forecast_from: date) -> int:
    """The actual net (income minus spending) of the cut's month before the cut. Serving reads it
    from dated rows; a weekly ledger has only weekly totals, so each week counts by its share of
    days in [first of the month, cut)."""
    first = date(forecast_from.year, forecast_from.month, 1)
    net = 0.0
    for week in range(series.weeks):
        monday = series.start + timedelta(days=DAYS_PER_WEEK * week)
        days = sum(
            first <= monday + timedelta(days=d) < forecast_from for d in range(DAYS_PER_WEEK)
        )
        if days:
            net += (float(series.income[week]) - float(series.spend[week])) * days / DAYS_PER_WEEK
    return round(net)


class _Replay:
    """A 'forecaster' that returns the realised held-back weeks, so the realised outcome goes
    through exactly the served margin and shortfall code."""

    name = "realised"

    def __init__(self, spend: np.ndarray, income: np.ndarray) -> None:
        self._values = {"spend": np.asarray(spend, float), "income": np.asarray(income, float)}

    def for_kind(self, kind: str) -> "_Replay._One":
        return _Replay._One(self._values[kind])

    class _One:
        name = "realised"

        def __init__(self, values: np.ndarray) -> None:
            self._values = values

        def forecast(self, history: np.ndarray, horizon: int, start: date) -> np.ndarray:
            return self._values[:horizon]


def _simulate(series, forecaster, spend_errors, income_errors, end, mtd, seed, paths, fallback):
    start = _forecast_from(series)
    return simulate(
        series,
        known_flows([], [], start, end),  # the weekly cohort has no bills, plans or known income
        forecaster,
        spend_errors,
        income_errors,
        start,
        end,
        paths,
        seed,
        month_to_date_sen=mtd,
        fallback_errors=fallback,
        max_weeks=HORIZON,  # never past the held-back weeks
    )


def _realised(series, spend_next, income_next, end, month_to_date):
    none = np.zeros(0)
    replay = _Replay(spend_next, income_next)
    return _simulate(series, replay, none, none, end, month_to_date, 0, 1, False)


def realised_shortfall(
    series: WeeklySeries,
    spend_next: np.ndarray,
    income_next: np.ndarray,
    end: date,
    month_to_date: int,
) -> bool:
    """Did the realised running margin go below RM0 at a month-end, by the served definition?"""
    return _realised(series, spend_next, income_next, end, month_to_date).p_shortfall == 1.0


def served_p(
    series: WeeklySeries,
    forecaster: Forecaster,
    end: date,
    month_to_date: int,
    seed: int,
    paths: int = PATHS,
) -> tuple[float, bool]:
    """(P(shortfall), whether the error record came from the fallback), built as
    `service.prepare_ledger` builds it."""
    spend_errors, spend_fallback = error_record(series.spend, series.start, forecaster, "spend")
    income_errors, income_fallback = error_record(series.income, series.start, forecaster, "income")
    fallback = spend_fallback or income_fallback
    result = _simulate(
        series,
        forecaster,
        widen(spend_errors, inflation_for(series.weeks, "spend")),
        widen(income_errors, inflation_for(series.weeks, "income")),
        end,
        month_to_date,
        seed,
        paths,
        fallback,
    )
    return result.p_shortfall, fallback


@dataclass(frozen=True)
class Case:
    profile: int
    cut: int
    weeks: int  # weeks of history before the cut
    realised: bool
    p: dict[str, float]
    fallback: dict[str, bool]
    months: tuple[str, ...]  # the month-ends checked
    cut_date: date  # the first forecast day (a Monday)
    month_to_date: int  # sen: the actual net of the cut's month before the cut
    realised_first: bool  # the realised running margin was below RM0 at the FIRST month-end


def cases_for_student(
    profile: int,
    spend: np.ndarray,
    income: np.ndarray,
    start: date,
    forecasters: Mapping[str, Forecaster],
    cuts: Sequence[int] = CUTS,
    seed: int = SEED,
) -> list[Case]:
    out = []
    for cut in cuts:
        at = len(spend) - cut
        spend_next, income_next = spend[at : at + HORIZON], income[at : at + HORIZON]
        forecast_from = start + timedelta(days=DAYS_PER_WEEK * at)
        end = forecast_from + timedelta(days=DAYS_PER_WEEK * HORIZON - 1)
        for weeks in history_lengths(profile, cut, at, seed):
            if weeks < MIN_SERIES_WEEKS:
                continue
            first = at - weeks
            series = WeeklySeries(
                start + timedelta(days=DAYS_PER_WEEK * first),
                np.rint(spend[first:at]).astype(np.int64),
                np.rint(income[first:at]).astype(np.int64),
            )
            mtd = month_to_date_sen(series, forecast_from)
            realised = _realised(series, spend_next, income_next, end, mtd)
            p, fallback = {}, {}
            for name, forecaster in forecasters.items():
                p[name], fallback[name] = served_p(
                    series, forecaster, end, mtd, case_seed(profile, cut, weeks)
                )
            short = realised.p_shortfall == 1.0
            first = bool(realised.p_negative_by_month) and realised.p_negative_by_month[0] == 1.0
            out.append(
                Case(profile, cut, weeks, short, p, fallback, tuple(realised.months),
                     forecast_from, mtd, first)
            )  # fmt: skip
    return out


def collect(
    path: Path, profiles: Iterable[int], forecasters: Mapping[str, Forecaster]
) -> list[Case]:
    cases: list[Case] = []
    pending = {}
    for series in load_synthetic(path, profile_ids=set(profiles)):
        pending[series.kind] = series
        if len(pending) == 2:
            spend, income = pending.pop("spend"), pending.pop("income")
            profile = int(spend.series_id.split("-")[1])
            cases.extend(
                cases_for_student(profile, spend.values, income.values, spend.start, forecasters)
            )
    return cases


# --- scores ---------------------------------------------------------------------------------------


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def log_loss(p: np.ndarray, y: np.ndarray, eps: float = EPS) -> float:
    q = np.clip(np.asarray(p, float), eps, 1 - eps)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))


def auc(p: np.ndarray, y: np.ndarray) -> float | None:
    """Mann-Whitney AUC, ties counted as half; None when only one outcome occurs."""
    p, y = np.asarray(p, float), np.asarray(y, bool)
    pos, neg = p[y], p[~y]
    if not len(pos) or not len(neg):
        return None
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    values = np.concatenate([pos, neg])[order]
    ranks = np.empty(len(values))
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[j + 1] == values[i]:
            j += 1
        ranks[i : j + 1] = (i + j) / 2 + 1
        i = j + 1
    rank_of = np.empty(len(values))
    rank_of[order] = ranks
    pos_ranks = rank_of[: len(pos)].sum()
    return float((pos_ranks - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def _bin_index(p: np.ndarray, bins: int = BINS) -> np.ndarray:
    return np.minimum((np.asarray(p, float) * bins).astype(int), bins - 1)


def ece(p: np.ndarray, y: np.ndarray, bins: int = BINS) -> float:
    """Expected calibration error over equal-width probability bins (1.0 in the last one)."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    index = _bin_index(p, bins)
    total = 0.0
    for b in range(bins):
        inside = index == b
        if inside.any():
            total += inside.sum() * abs(p[inside].mean() - y[inside].mean())
    return float(total / len(p))


@dataclass(frozen=True)
class CalibrationRow:
    label: str
    cases: int
    mean_p: float | None
    realised: float | None


def calibration_rows(p: np.ndarray, y: np.ndarray, bins: int = BINS) -> list[CalibrationRow]:
    """P exactly 0, the ten bins strictly between, P exactly 1."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    masks = [("0 exactly", p == 0.0)]
    for b in range(bins):
        low, high = b / bins, (b + 1) / bins
        label = f"(0, {high:g})" if b == 0 else f"[{low:g}, {high:g})"
        if b == bins - 1:
            label = f"[{low:g}, 1)"
        masks.append((label, (p > 0) & (p < 1) & (p >= low) & (p < high)))
    masks.append(("1 exactly", p == 1.0))
    rows = []
    for label, mask in masks:
        n = int(mask.sum())
        rows.append(
            CalibrationRow(
                label,
                n,
                float(p[mask].mean()) if n else None,
                float(y[mask].mean()) if n else None,
            )
        )
    return rows


def band_rows(p: np.ndarray, y: np.ndarray) -> dict[str, tuple[int, int]]:
    """Per served band: (cases, realised shortfalls)."""
    bands = np.array([band(float(v)) for v in p])
    y = np.asarray(y, bool)
    return {b: (int((bands == b).sum()), int((y & (bands == b)).sum())) for b in BANDS}


def share_exact(p: np.ndarray) -> tuple[float, float]:
    p = np.asarray(p, float)
    return float(np.mean(p == 0.0)), float(np.mean(p == 1.0))


def confident_misses(p: np.ndarray, y: np.ndarray) -> int:
    """Cases the engine was certain about and wrong: P = 0 but short, or P = 1 but not short."""
    p, y = np.asarray(p, float), np.asarray(y, bool)
    return int(((p == 0.0) & y).sum() + ((p == 1.0) & ~y).sum())


def paired_bootstrap(
    loss_a: np.ndarray, loss_b: np.ndarray, groups: np.ndarray, draws: int, seed: int
) -> tuple[float, float, float]:
    """Mean of (a - b) over students and a 95% percentile interval from resampling STUDENTS (a
    student's cases are not independent of each other)."""
    diff = np.asarray(loss_a, float) - np.asarray(loss_b, float)
    groups = np.asarray(groups)
    ids = np.unique(groups)
    per_student = np.array([diff[groups == g].mean() for g in ids])
    rng = np.random.default_rng(seed)
    means = per_student[rng.integers(0, len(ids), size=(draws, len(ids)))].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(per_student.mean()), float(low), float(high)


# --- summary and page -----------------------------------------------------------------------------


def _bucket_label(index: int) -> str:
    low, high = BUCKET_RANGES[index]
    return f"{low}+" if high is None else f"{low}-{high}"


def _arrays(cases: Sequence[Case], base_rate: float) -> dict[str, np.ndarray]:
    out = {name: np.array([c.p[name] for c in cases], float) for name in METHODS}
    out["constant"] = np.full(len(cases), base_rate)
    return out


def _metrics(p: np.ndarray, y: np.ndarray, base_rate: float) -> dict:
    constant = brier(np.full(len(y), base_rate), y)
    score = brier(p, y)
    zero, one = share_exact(p)
    return {
        "mean_p": float(np.mean(p)),
        "brier": score,
        "brier_skill": 1 - score / constant if constant > 0 else 0.0,
        "log_loss": log_loss(p, y),
        "auc": auc(p, y),
        "ece": ece(p, y),
        "share_p0": zero,
        "share_p1": one,
        "confident_misses": confident_misses(p, y),
    }


MONTH_SO_FAR = ("negative", "zero or positive")


def _slices(cases: Sequence[Case], cut: int) -> list[tuple[str, str, list[Case]]]:
    """(group, label, cases): all; each history bucket; the sign of the month so far at the cut."""
    at_cut = [c for c in cases if c.cut == cut]
    out = [("all", "all", at_cut)]
    for b in range(len(BUCKET_RANGES)):
        out.append(("history", _bucket_label(b), [c for c in at_cut if bucket_of(c.weeks) == b]))
    out.append(("month_so_far", MONTH_SO_FAR[0], [c for c in at_cut if c.month_to_date < 0]))
    out.append(("month_so_far", MONTH_SO_FAR[1], [c for c in at_cut if c.month_to_date >= 0]))
    return out


def _base_rate(cases: Sequence[Case], cut: int) -> float:
    return float(np.mean([c.realised for c in cases if c.cut == cut]))


def summary_rows(cases: Sequence[Case]) -> list[dict]:
    """One row per cut, slice and method; the constant is the slice's own realised rate."""
    rows = []
    for cut in sorted({c.cut for c in cases}):
        for group, label, part in _slices(cases, cut):
            if not part:
                continue
            y = np.array([c.realised for c in part])
            base = float(y.mean())
            for method, p in _arrays(part, base).items():
                rows.append(
                    {
                        "cut": cut,
                        "group": group,
                        "slice": label,
                        "method": method,
                        "cases": len(part),
                        "students": len({c.profile for c in part}),
                        "realised_rate": base,
                        **_metrics(p, y, base),
                    }
                )
    return rows


def _f(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _headline(rows: list[dict], history: str) -> list[str]:
    out = [
        "| method | cases | mean P | Brier | Brier skill vs constant | log loss | AUC | ECE | "
        "P exactly 0 | P exactly 1 | confident misses |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["slice"] != history:
            continue
        out.append(
            f"| {LABELS[r['method']]} | {r['cases']} | {_f(r['mean_p'])} | {_f(r['brier'], 4)} | "
            f"{r['brier_skill']:+.3f} | {_f(r['log_loss'])} | {_f(r['auc'])} | {_f(r['ece'])} | "
            f"{_f(r['share_p0'])} | {_f(r['share_p1'])} | {r['confident_misses']} |"
        )
    return out


def _by_slice(rows: list[dict], group: str, title: str) -> list[str]:
    out = [
        f"| {title} | method | cases | realised rate | mean P | Brier | Brier skill | AUC | ECE "
        "| P exactly 0 | P exactly 1 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["group"] != group:
            continue
        out.append(
            f"| {r['slice']} | {LABELS[r['method']]} | {r['cases']} | {_f(r['realised_rate'])} "
            f"| {_f(r['mean_p'])} | {_f(r['brier'], 4)} | {r['brier_skill']:+.3f} | "
            f"{_f(r['auc'])} | {_f(r['ece'])} | {_f(r['share_p0'])} | {_f(r['share_p1'])} |"
        )
    return out


def _calibration(part: Sequence[Case]) -> list[str]:
    y = np.array([c.realised for c in part])
    tables = {m: calibration_rows(np.array([c.p[m] for c in part]), y) for m in METHODS}
    out = [
        "| P(shortfall) | served LSTM: cases | mean P | realised rate | MA13: cases | mean P | "
        "realised rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for a, b in zip(tables["lstm"], tables["ma13"], strict=True):
        out.append(
            f"| {a.label} | {a.cases} | {_f(a.mean_p)} | {_f(a.realised)} | {b.cases} | "
            f"{_f(b.mean_p)} | {_f(b.realised)} |"
        )
    return out


def _bands(part: Sequence[Case], base: float) -> list[str]:
    y = np.array([c.realised for c in part])
    out = [
        "| method | band | cases | realised short | realised not short | realised rate |",
        "|---|---|---|---|---|---|",
    ]
    for method, p in _arrays(part, base).items():
        for name, (n, short) in band_rows(p, y).items():
            rate = _f(short / n) if n else "-"
            out.append(f"| {LABELS[method]} | {name} | {n} | {short} | {n - short} | {rate} |")
    return out


def _bootstrap(part: Sequence[Case], base: float, cut: int) -> list[str]:
    y = np.array([c.realised for c in part], float)
    groups = np.array([c.profile for c in part])
    loss = {m: (p - y) ** 2 for m, p in _arrays(part, base).items()}
    out = []
    for other in ("ma13", "constant"):
        point, low, high = paired_bootstrap(
            loss["lstm"], loss[other], groups, BOOTSTRAP_DRAWS, SEED + cut
        )
        out.append(
            f"- Brier, served LSTM minus {LABELS[other]}: {point:+.4f} "
            f"(95% interval over students {low:+.4f} to {high:+.4f}; below 0 = the LSTM is "
            "better)."
        )
    return out


def _lowest(rows: list[dict]) -> list[str]:
    out = []
    for history in dict.fromkeys(r["slice"] for r in rows if r["group"] != "month_so_far"):
        part = [r for r in rows if r["slice"] == history]
        best = min(part, key=lambda r: r["brier"])
        out.append(f"{history}: {LABELS[best['method']]}")
    return out


def render(cases: Sequence[Case], ids: Sequence[int]) -> str:
    rows = summary_rows(cases)
    lines = [
        "# Outcome check: the served P(shortfall) against what really happened",
        "",
        "> Generated by `python -m ml.engine1_eval.outcome_check` - do not edit by hand.",
        "",
        f"{len(ids)} synthetic development students (cohort indices {EVAL_POOL}-{COHORT - 1}, not "
        f"divisible by {LOCKBOX_EVERY}: never Engine 2's lockbox; none of the 60 Engine 1 test "
        f"students, the {FRESH_PROFILES} fresh-check students or the {DEV_PROFILES} students the "
        "served band table was fitted on). Evaluation only: nothing was fitted, chosen or "
        "changed.",
        "",
        f"Each ledger is cut {' and '.join(str(c) for c in CUTS)} weeks before its end. At the "
        "cut the script builds what serving builds: the user's own error record widened by the "
        f"served band table, the served forecast and the same {PATHS}-path Monte Carlo. "
        "P(shortfall) is the share of paths whose running margin (from RM0 at the start of the "
        "cut's month, plus the month so far) is below RM0 at any month-end inside the next "
        f"{HORIZON} weeks. The **realised** outcome is the same code run on the {HORIZON} "
        "held-back weeks. History length is varied by starting the ledger later: one case per "
        f"student, cut and bucket ({', '.join(_bucket_label(b) for b in range(len(BUCKETS)))} "
        "weeks; 52+ is the whole history before the cut). Benchmarks: a **constant** (the "
        "realised rate of these students at that cut: in-sample, the best any constant can "
        "do) and **MA13** run through the same simulation instead of the LSTM.",
        "",
        f"Log loss clips P to {EPS:g} from 0 and 1 (half a simulated path). ECE is the expected "
        f"calibration error over {BINS} equal-width probability bins. Confident misses: P "
        "exactly 0 and short, or P exactly 1 and not short. Bands: Safe below "
        f"{SAFE_BELOW:.2f}, Caution below {CAUTION_BELOW:.2f}, At Risk from there.",
        "",
    ]
    for cut in CUTS:
        part = [c for c in cases if c.cut == cut]
        if not part:
            continue
        base = _base_rate(cases, cut)
        cut_rows = [r for r in rows if r["cut"] == cut]
        months = sorted({m for c in part for m in c.months})
        fallback = {m: float(np.mean([c.fallback[m] for c in part])) for m in METHODS}
        cut_dates = ", ".join(sorted({c.cut_date.isoformat() for c in part}))
        shorts = [c for c in part if c.realised]
        first = float(np.mean([c.realised_first for c in shorts])) if shorts else None
        negative = float(np.mean([c.month_to_date < 0 for c in part]))
        lines += [
            f"## Cut {cut} weeks before the end",
            "",
            f"Forecast from {cut_dates}; month-ends checked: {', '.join(months)}. {len(part)} "
            f"cases from {len({c.profile for c in part})} students; realised shortfall rate "
            f"(the constant) {base:.3f}. Share of cases whose error record came from the "
            f"fallback: served LSTM {fallback['lstm']:.3f}, MA13 {fallback['ma13']:.3f}.",
            "",
            "The first month-end is the cut's own month, so it is mostly decided by the actual "
            "month so far, which the simulation is given. Share of realised shortfalls already "
            f"below RM0 at the first month-end: {_f(first)}. Share of cases whose month so far "
            f"was negative at the cut: {negative:.3f}. The table *By the month so far* separates "
            "the two.",
            "",
            "### All history lengths",
            "",
            *_headline(cut_rows, "all"),
            "",
            *_bootstrap(part, base, cut),
            f"- Lowest Brier by history length: {'; '.join(_lowest(cut_rows))}.",
            "",
            "### By weeks of history",
            "",
            *_by_slice(cut_rows, "history", "weeks of history"),
            "",
            "### By the month so far at the cut",
            "",
            "Here the constant is each row's own realised rate (the best constant that knows the "
            "sign of the month so far).",
            "",
            *_by_slice(cut_rows, "month_so_far", "month so far"),
            "",
            "### Calibration (all history lengths)",
            "",
            *_calibration(part),
            "",
            "### Served band against the realised outcome (all history lengths)",
            "",
            *_bands(part, base),
            "",
        ]
    lines += [
        "## Limits",
        "",
        "- Synthetic students only. Every student in the cohort shares one calendar, so each cut "
        "tests one season (the month-ends above), not the whole year.",
        "- The weekly cohort holds discretionary spending and ALL income, and no bills, BNPL "
        "plans or confirmed recurring items. Known flows are therefore zero and the margin is "
        "income minus discretionary spending: this checks the forecast-and-bootstrap part of "
        "P(shortfall), not the known-flows part. Serving forecasts only the income NOT covered "
        "by a confirmed recurring item; here the forecast covers all of it.",
        "- The month so far is the cut month's share of the weekly totals, apportioned by days; "
        "serving reads it from dated rows.",
        "- A shorter history is the same student starting to log later, so the buckets share "
        "students and outcomes; they are not independent samples.",
        "- The constant is in-sample (the realised rate of the scored students), which favours it.",
        "",
    ]
    return "\n".join(lines)


def write_csv(rows: Sequence[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {k: (round(v, 6) if isinstance(v, float) else v) for k, v in row.items()}
            )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Score served P(shortfall) against outcomes.")
    parser.add_argument("--synthetic", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--profiles", type=int, default=OUTCOME_PROFILES)
    parser.add_argument("--out-report", type=Path, default=REPORT)
    parser.add_argument("--out-table", type=Path, default=TABLE)
    args = parser.parse_args(argv)
    began = time.perf_counter()
    ids = outcome_profiles(args.profiles)
    forecasters = {name: served_forecaster(name) for name in METHODS}
    cases = collect(args.synthetic, ids, forecasters)
    args.out_report.write_text(render(cases, ids), encoding="utf-8", newline="\n")
    write_csv(summary_rows(cases), args.out_table)
    seconds = time.perf_counter() - began
    print(f"wrote {args.out_report}, {args.out_table}: {len(cases)} cases, {seconds:.1f} s")  # noqa: T201


if __name__ == "__main__":
    main()
