"""Streaming statistics over generated profiles, and the moments table built from them (A12).

The collector sees one profile at a time and keeps only aggregates, so a 10,000-profile report
does not need 10,000 profiles in memory. Every row of the moments table is a generated number set
beside its target; rows are reported whether or not they flatter the generator.
"""

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median
from typing import Any

from app.domain.categorize import REFUND, TRANSFER
from ml.datagen.bnpl import NAMED_PROVIDERS, PROVIDERS
from ml.datagen.export import WeekPoint, weekly_series
from ml.datagen.income import PTPTN_DESCRIPTION
from ml.datagen.params import Params
from ml.datagen.profile import PERSONAS, StudentProfile

RELATIVE_TOLERANCE = 0.15  # for amounts with a cited target (spend level)
SHARE_TOLERANCE = 0.05  # absolute, for shares that have no sampling-noise allowance
SPEND_SHARE_TOLERANCE = 0.15  # relative, for category shares of spend
NOISE_SIGMAS = 3  # sampling-noise allowance on proportions
ROUNDING_SEN = 1  # a lump times its disbursement count may be a sen away from the table value


@dataclass
class Collector:
    params: Params
    personas: Counter = field(default_factory=Counter)
    owners: Counter = field(default_factory=Counter)
    monthly_spend: dict[str, list[int]] = field(default_factory=dict)
    monthly_income: dict[str, list[int]] = field(default_factory=dict)
    category_spend: Counter = field(default_factory=Counter)
    on_time: int = 0  # instalment level (context only)
    late: int = 0
    unpaid: int = 0
    holders_on_time: int = 0  # holder level: what the cited study measured
    holders_late: int = 0
    holders_missed: int = 0
    provider_plans: Counter = field(default_factory=Counter)
    option_ok: Counter = field(default_factory=Counter)
    fee_ok: Counter = field(default_factory=Counter)
    max_limit: dict[str, int] = field(default_factory=dict)
    ratios: list[float] = field(default_factory=list)
    purchases: int = 0
    limit_capped: int = 0
    ptptn_lumps: int = 0
    ptptn_matches: int = 0
    examples: dict[str, list[WeekPoint]] = field(default_factory=dict)
    profiles: int = 0

    def add(self, profile: StudentProfile) -> None:
        self.profiles += 1
        persona = profile.persona
        self.personas[persona] += 1
        if profile.bnpl.plans:
            self.owners[persona] += 1
        self._monthly(profile)
        self._categories(profile)
        self._plans(profile)
        self._purchase(profile)
        self._ptptn(profile)
        if persona not in self.examples:
            self.examples[persona] = weekly_series(profile)

    def _monthly(self, profile: StudentProfile) -> None:
        spend: dict[tuple[int, int], int] = {}
        income: dict[tuple[int, int], int] = {}
        for t in profile.discretionary_events:
            if t.category == TRANSFER:
                continue
            sign = -1 if t.category == REFUND else 1
            key = (t.date.year, t.date.month)
            spend[key] = spend.get(key, 0) + sign * t.amount_sen
        for t in profile.income_events:
            key = (t.date.year, t.date.month)
            income[key] = income.get(key, 0) + t.amount_sen
        for year, month in _complete_months(profile.start, profile.as_of):
            self.monthly_spend.setdefault(profile.persona, []).append(
                max(spend.get((year, month), 0), 0)
            )
            self.monthly_income.setdefault(profile.persona, []).append(income.get((year, month), 0))

    def _categories(self, profile: StudentProfile) -> None:
        for t in profile.discretionary_events:
            if t.type == "expense" and t.category != TRANSFER:
                self.category_spend[t.category] += t.amount_sen

    def _plans(self, profile: StudentProfile) -> None:
        rate = self.params["bnpl.long_plan_fee_rate_pct"]
        for plan in profile.bnpl.plans:
            p = plan.proposal
            self.provider_plans[p.provider] += 1
            options = self.params[f"bnpl.instalment_options.{p.provider}"]
            self.option_ok[p.provider] += p.num_installments in options
            if p.provider in NAMED_PROVIDERS:
                free = self.params[f"bnpl.zero_fee_instalments.{p.provider}"]
                expected = 0 if p.num_installments in free else rate
                self.fee_ok[p.provider] += p.monthly_fee_rate_pct == expected
            for seq, instalment in enumerate(p.instalments, start=1):
                if (
                    instalment.paid_at_checkout
                    or not profile.start <= instalment.due_date <= profile.as_of
                ):
                    continue
                paid_on = plan.paid_dates.get(seq)
                if paid_on is None:
                    self.unpaid += 1
                elif paid_on == instalment.due_date:
                    self.on_time += 1
                else:
                    self.late += 1
        self._holder(profile)
        for provider, limit in profile.bnpl.limits.items():
            if limit is not None:
                self.max_limit[provider] = max(self.max_limit.get(provider, 0), limit)

    def _holder(self, profile: StudentProfile) -> None:
        """One verdict per account holder, over instalments whose outcome is already known."""
        _, high = self.params["repayment.late_days_range"]
        cutoff = profile.as_of - timedelta(days=high)
        outcomes = [
            (plan.paid_dates.get(seq), instalment.due_date)
            for plan in profile.bnpl.plans
            for seq, instalment in enumerate(plan.proposal.instalments, start=1)
            if not instalment.paid_at_checkout and instalment.due_date <= cutoff
        ]
        if not outcomes:
            return
        if any(paid is None for paid, _ in outcomes):
            self.holders_missed += 1
        elif any(paid != due for paid, due in outcomes):
            self.holders_late += 1
        else:
            self.holders_on_time += 1

    def _purchase(self, profile: StudentProfile) -> None:
        income = max(profile.expected_monthly_income_sen, 1)
        self.ratios.append(profile.purchase.price_sen / income)
        self.purchases += 1
        self.limit_capped += profile.purchase.proposal.upfront_sen > 0

    def _ptptn(self, profile: StudentProfile) -> None:
        table = self.params["income.ptptn_annual_sen"]
        per_year = self.params["income.ptptn_disbursements_per_year"]
        for t in profile.income_events:
            if t.description == PTPTN_DESCRIPTION:
                self.ptptn_lumps += 1
                self.ptptn_matches += any(
                    abs(t.amount_sen * per_year - annual) <= ROUNDING_SEN * per_year
                    for annual in table
                )


def _complete_months(start: date, as_of: date) -> list[tuple[int, int]]:
    months = []
    cursor = start.replace(day=1)
    while cursor <= as_of:
        following = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        if following - timedelta(days=1) <= as_of:
            months.append((cursor.year, cursor.month))
        cursor = following
    return months


def _noise(p: float, n: int) -> float:
    return NOISE_SIGMAS * math.sqrt(max(p * (1 - p), 1e-9) / max(n, 1))


def _row(
    param: str,
    description: str,
    unit: str,
    kind: str,
    target: Any,
    measured: Any,
    *,
    tolerance: float | None = None,
    relative: bool = False,
    upper_bound: bool = False,
    note: str = "",
) -> dict[str, Any]:
    status = "no target"
    if target is not None and measured is None:
        status = "not measured"  # a cited figure the run never exercised: flagged, not hidden
    if target is not None and measured is not None:
        if upper_bound:
            ok = measured <= target
        else:
            allowed = tolerance if tolerance is not None else SHARE_TOLERANCE
            gap = (
                abs(measured - target) / (abs(target) or 1) if relative else abs(measured - target)
            )
            ok = gap <= allowed
        status = "within tolerance" if ok else "outside tolerance"
    return {
        "param": param,
        "description": description,
        "unit": unit,
        "kind": kind,
        "target": "" if target is None else _fmt(target),
        "measured": "" if measured is None else _fmt(measured),
        "status": status,
        "note": note,
    }


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _share(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def moments(c: Collector) -> list[dict[str, Any]]:
    """Every cited parameter first, then the assumed ones whose effect can be measured."""
    return [
        *_level_rows(c),
        *_category_rows(c),
        *_bnpl_rows(c),
        *_repayment_rows(c),
        *_assumed_rows(c),
    ]


def _level_rows(c: Collector) -> list[dict[str, Any]]:
    p = c.params
    rows: list[dict[str, Any]] = []
    rows.append(
        _row(
            "income.ptptn_annual_sen",
            "PTPTN lump sums (x disbursements per year) equal a cited annual amount",
            "share",
            "cited (wiring check)",
            1.0,
            _share(c.ptptn_matches, c.ptptn_lumps),
            tolerance=0.0,
            note=f"{c.ptptn_lumps} lump sums",
        )
    )
    spend = c.monthly_spend.get("budget_conscious", [])
    rows.append(
        _row(
            "discretionary.monthly_median_sen.budget_conscious",
            "Median monthly discretionary spend, budget-conscious persona",
            "sen",
            "cited",
            p["discretionary.monthly_median_sen.budget_conscious"],
            int(median(spend)) if spend else None,
            tolerance=RELATIVE_TOLERANCE,
            relative=True,
            note="target is the midpoint of a modal band (RM201-400), not a bound",
        )
    )
    return rows


def _category_rows(c: Collector) -> list[dict[str, Any]]:
    p = c.params
    total = sum(c.category_spend.values())
    food_w = p["discretionary.category_weight_food"] + p["discretionary.category_weight_eating_out"]
    transport_w = p["discretionary.category_weight_transport"]
    other = p["discretionary.category_other_share"]
    scale = (1 - other) / (food_w + transport_w)
    split_total = sum(
        p[f"discretionary.other_split_{n}"] for n in ("shopping", "entertainment", "education")
    )

    def row(param: str, text: str, target: float | None, name: str, kind: str, note: str = ""):
        measured = _share(c.category_spend[name], total) if name else None
        return _row(
            param,
            text,
            "share",
            kind,
            target,
            measured,
            tolerance=SPEND_SHARE_TOLERANCE,
            relative=True,
            note=note,
        )

    rows = [
        row(
            "discretionary.category_weight_food",
            "Food (food plus eating out) share of spend",
            food_w * scale,
            "Food",
            "cited",
            "food and eating out are one generated category",
        ),
        _row(
            "discretionary.category_weight_eating_out",
            "Eating out (generated together with food, see the row above)",
            "share",
            "cited",
            None,
            None,
            note="measured jointly with category_weight_food",
        ),
        row(
            "discretionary.category_weight_transport",
            "Transport share of spend",
            transport_w * scale,
            "Transport",
            "cited",
        ),
    ]
    for name in ("shopping", "entertainment", "education"):
        target = other * p[f"discretionary.other_split_{name}"] / split_total
        rows.append(
            row(
                f"discretionary.other_split_{name}",
                f"{name.title()} share of spend",
                target,
                name.title(),
                "assumed",
            )
        )
    ratio_target = food_w / transport_w
    ratio = _share(c.category_spend["Food"], c.category_spend["Transport"])
    rows.append(
        _row(
            "derived.food_to_transport_spend_ratio",
            "Food to transport spend ratio (cited weights imply this ratio)",
            "ratio",
            "derived",
            round(ratio_target, 4),
            None if ratio is None else round(ratio, 4),
            tolerance=SPEND_SHARE_TOLERANCE,
            relative=True,
        )
    )
    return rows


def _bnpl_rows(c: Collector) -> list[dict[str, Any]]:
    p = c.params
    rows: list[dict[str, Any]] = []
    for provider in NAMED_PROVIDERS:
        n = c.provider_plans[provider]
        rows.append(
            _row(
                f"bnpl.instalment_options.{provider}",
                f"{provider}: plans use an instalment count the provider offers",
                "share",
                "cited (wiring check)",
                1.0,
                _share(c.option_ok[provider], n),
                tolerance=0.0,
                note=f"{n} plans",
            )
        )
    for provider in NAMED_PROVIDERS:
        n = c.provider_plans[provider]
        rows.append(
            _row(
                f"bnpl.zero_fee_instalments.{provider}",
                f"{provider}: fee is zero on zero-fee counts and the long-plan rate otherwise",
                "share",
                "cited (wiring check)",
                1.0,
                _share(c.fee_ok[provider], n),
                tolerance=0.0,
                note=f"{n} plans",
            )
        )
    named_plans = sum(c.provider_plans[q] for q in NAMED_PROVIDERS)
    rows.append(
        _row(
            "bnpl.long_plan_fee_rate_pct",
            "Long plans carry the cited monthly fee rate (checked together with the zero-fee rows)",
            "share",
            "cited (wiring check)",
            1.0,
            _share(sum(c.fee_ok.values()), named_plans),
            tolerance=0.0,
        )
    )
    for provider in ("spaylater", "tiktok_paylater"):
        cap = p[f"bnpl.limit_cap_sen.{provider}"]
        rows.append(
            _row(
                f"bnpl.limit_cap_sen.{provider}",
                f"{provider}: largest recorded limit never exceeds the documented cap",
                "sen",
                "cited (wiring check)",
                cap,
                c.max_limit.get(provider),
                upper_bound=True,
            )
        )
    return rows


def _repayment_rows(c: Collector) -> list[dict[str, Any]]:
    """The cited figures describe account HOLDERS, so they are compared with holder shares."""
    p = c.params
    holders = c.holders_on_time + c.holders_late + c.holders_missed
    norm = (
        p["repayment.on_time_share"]
        + p["repayment.late_but_paid_share"]
        + p["repayment.missed_share"]
    )
    note = f"{holders} holders with a settled instalment; the generator adds an assumed miss share"
    rows = []
    for param, text, count in (
        ("repayment.on_time_share", "Holders who paid every instalment on time", c.holders_on_time),
        ("repayment.late_but_paid_share", "Holders who paid late but in full", c.holders_late),
        (
            "repayment.missed_share",
            "Holders with an unpaid instalment (cited: under 0.5%)",
            c.holders_missed,
        ),
    ):
        target = p[param] / norm  # what the generator should produce once the miss share is added
        rows.append(
            _row(
                param,
                text,
                "share",
                "assumed" if param.endswith("missed_share") else "cited",
                p[param] if param != "repayment.missed_share" else p[param],
                _share(count, holders),
                tolerance=max(0.03, _noise(target, holders)) if holders else SHARE_TOLERANCE,
                note=note,
            )
        )
    inst = c.on_time + c.late + c.unpaid
    rows.append(
        _row(
            "derived.instalment_on_time_share",
            "Instalments paid on the due date (not what the study measured; context only)",
            "share",
            "derived",
            None,
            _share(c.on_time, inst),
            note=f"{inst} instalments",
        )
    )
    return rows


def _assumed_rows(c: Collector) -> list[dict[str, Any]]:
    p = c.params
    rows = []
    for persona in PERSONAS:
        rows.append(
            _row(
                f"population.persona_weights.{persona}",
                f"Share of profiles in the {persona} persona",
                "share",
                "assumed",
                p[f"population.persona_weights.{persona}"],
                _share(c.personas[persona], c.profiles),
                tolerance=_noise(p[f"population.persona_weights.{persona}"], c.profiles),
            )
        )
    for persona in PERSONAS:
        rows.append(
            _row(
                f"bnpl.ownership_probability.{persona}",
                f"Share of {persona} profiles holding any BNPL plan",
                "share",
                "assumed",
                p[f"bnpl.ownership_probability.{persona}"],
                _share(c.owners[persona], c.personas[persona]),
                tolerance=_noise(p[f"bnpl.ownership_probability.{persona}"], c.personas[persona]),
            )
        )
    total_plans = sum(c.provider_plans.values())
    for provider in PROVIDERS:
        rows.append(
            _row(
                f"bnpl.provider_weights.{provider}",
                f"Share of plans on {provider}",
                "share",
                "assumed",
                p[f"bnpl.provider_weights.{provider}"],
                _share(c.provider_plans[provider], total_plans),
                tolerance=_noise(p[f"bnpl.provider_weights.{provider}"], total_plans),
            )
        )
    for persona in PERSONAS:
        income = c.monthly_income.get(persona, [])
        rows.append(
            _row(
                f"derived.monthly_income_median.{persona}",
                f"Median monthly income, {persona} persona (no cited target)",
                "sen",
                "derived",
                None,
                int(median(income)) if income else None,
            )
        )
    if c.ratios:
        ordered = sorted(c.ratios)
        low, high = p["purchase.price_to_monthly_income_range"]
        rows.append(
            _row(
                "purchase.price_to_monthly_income_range",
                "Smallest and largest proposed price as a multiple of monthly income "
                "(range is a coverage choice, not an estimate)",
                "ratio",
                "assumed",
                high,
                round(ordered[-1], 4),
                upper_bound=True,
                note=f"smallest {ordered[0]:.4f} (range starts at {low})",
            )
        )
        rows.append(
            _row(
                "derived.purchase_limit_capped_share",
                "Share of proposed purchases split by a provider limit (no cited target)",
                "share",
                "derived",
                None,
                _share(c.limit_capped, c.purchases),
            )
        )
    return rows
