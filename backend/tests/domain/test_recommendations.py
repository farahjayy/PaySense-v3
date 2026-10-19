"""Recommendations and alerts (WP15): every rule fires when it should and not otherwise, and every
figure in a sentence comes from the recommendation's own sources."""

import re
from datetime import date

import pytest

from app.domain.recommendations import RULES, Inputs, alerts, format_source, recommend

TODAY = date(2026, 3, 10)


def forecast(p=0.05, status="ok", band=None, worst="2026-05", months=6):
    band = band or ("Safe" if p < 0.1 else "Caution" if p < 0.3 else "At Risk")
    sim = {"p_shortfall": p, "worst_month": worst} if status == "ok" else None
    return {"status": status, "band": band if status == "ok" else None, "simulation": sim,
            "months_of_history": months}  # fmt: skip


def budget_item(category, limit, spent, state, projected=None, projected_state=None):
    return {"category": category, "limit_sen": limit, "spent_sen": spent, "state": state,
            "projected_sen": projected, "projected_state": projected_state}  # fmt: skip


def status(*items, month_spend=0):
    return {"items": list(items), "month_spend_sen": month_spend, "is_current": True}


def collision(start, end, total, names):
    return {"start": start, "end": end, "total_sen": total,
            "items": [{"name": n} for n in names]}  # fmt: skip


def bills(collisions=(), increases=()):
    return {"collisions": list(collisions), "increases": list(increases)}


def insights(movers=(), month="2026-02"):
    return {"month": month, "movers": list(movers)}


def limit(provider, limit_sen, used):
    return {"provider": provider, "limit_sen": limit_sen, "used_sen": used}


def base(**over) -> Inputs:
    values = {
        "today": TODAY,
        "forecast": forecast(),
        "budget_status": status(month_spend=1000),
        "budgets": [{"category": "Food"}],
        "bills": bills(),
        "insights": insights(),
        "limits": [],
    }
    return Inputs(**(values | over))


def fired(inputs: Inputs) -> set[str]:
    return {r.rule for r in recommend(inputs)}


# ------------------------------------------------------------------ one rule at a time
def test_nothing_fires_for_a_comfortable_month():
    assert fired(base()) == set()


@pytest.mark.parametrize(
    ("p", "severity", "is_alert"), [(0.12, "medium", False), (0.45, "high", True)]
)
def test_forecast_shortfall(p, severity, is_alert):
    inputs = base(forecast=forecast(p))
    (rec,) = recommend(inputs)
    assert (rec.rule, rec.severity) == ("forecast_shortfall", severity)
    assert [a.rule for a in alerts(inputs)] == (["forecast_shortfall"] if is_alert else [])


def test_forecast_shortfall_does_not_fire_below_the_safe_edge():
    assert "forecast_shortfall" not in fired(base(forecast=forecast(0.099)))


def test_a_locked_forecast_asks_for_history_instead():
    locked = forecast(status="locked", months=2)
    assert fired(base(forecast=locked)) == {"forecast_locked"}
    assert "forecast_locked" not in fired(base())


def test_budget_over_is_an_alert_and_near_is_not():
    over = status(budget_item("Food", 10_000, 12_000, "over"), month_spend=12_000)
    near = status(budget_item("Food", 10_000, 8_500, "near"), month_spend=8_500)
    pace = status(budget_item("Food", 10_000, 5_000, "ok", 12_500, "over"), month_spend=5_000)
    ok = status(budget_item("Food", 10_000, 2_000, "ok", 4_000, "ok"), month_spend=2_000)
    assert fired(base(budget_status=over)) == {"budget_over"}
    assert [a.rule for a in alerts(base(budget_status=over))] == ["budget_over"]
    assert fired(base(budget_status=near)) == {"budget_near"}
    assert alerts(base(budget_status=near)) == []
    assert fired(base(budget_status=pace)) == {"budget_near"}
    assert fired(base(budget_status=ok)) == set()


def test_a_collision_soon_is_an_alert_and_a_later_one_a_recommendation():
    soon = bills([collision("2026-03-12", "2026-03-18", 67_600, ["Phone", "Rent bilik"])])
    later = bills([collision("2026-03-30", "2026-04-05", 10_000, ["Bag", "Gym"])])
    assert fired(base(bills=soon)) == {"bill_collision"}
    assert [a.rule for a in alerts(base(bills=soon))] == ["bill_collision"]
    assert fired(base(bills=later)) == {"bill_collision"}
    assert alerts(base(bills=later)) == []
    assert fired(base(bills=bills())) == set()


def test_a_provider_limit_nearly_used():
    assert fired(base(limits=[limit("spaylater", 100_000, 85_000)])) == {"plan_near_limit"}
    assert fired(base(limits=[limit("spaylater", 100_000, 50_000)])) == set()
    assert fired(base(limits=[limit("spaylater", None, 90_000)])) == set()


def test_a_bill_increase():
    inc = {"name": "Unifi", "previous_sen": 9_900, "latest_sen": 10_900, "change_sen": 1_000,
           "change_pct": 0.101}  # fmt: skip
    assert fired(base(bills=bills(increases=[inc]))) == {"bill_increase"}


def test_spending_up_proposes_a_budget_only_when_none_exists():
    mover = {"category": "Shopping", "spend_sen": 30_000, "previous_sen": 20_000,
             "change_sen": 10_000, "change_pct": 0.5, "status": "up"}  # fmt: skip
    recs = recommend(base(insights=insights([mover]), budgets=[]))
    assert [r.rule for r in recs] == ["spending_up", "no_budgets"]
    rec = recs[0]
    assert rec.action.kind == "propose" and rec.action.action_type == "set_budget"
    assert rec.action.payload == {"category": "Shopping", "limit_sen": 20_000}
    (rec,) = recommend(base(insights=insights([mover]), budgets=[{"category": "shopping"}]))
    assert rec.action.kind == "link"
    small = mover | {"change_sen": 4_000, "spend_sen": 24_000, "change_pct": 0.2}
    assert fired(base(insights=insights([small]))) == set()


def test_no_budgets_with_spending_suggests_one():
    assert fired(base(budgets=[], budget_status=status(month_spend=5_000))) == {"no_budgets"}
    assert fired(base(budgets=[], budget_status=status(month_spend=0))) == set()


# ------------------------------------------------------------------ ordering and tracing
def everything() -> Inputs:
    mover = {"category": "Shopping", "spend_sen": 30_000, "previous_sen": 20_000,
             "change_sen": 10_000, "change_pct": 0.5, "status": "up"}  # fmt: skip
    inc = {"name": "Unifi", "previous_sen": 9_900, "latest_sen": 10_900, "change_sen": 1_000,
           "change_pct": 0.101}  # fmt: skip
    return base(
        forecast=forecast(0.62),
        budget_status=status(
            budget_item("Food", 10_000, 12_000, "over"),
            budget_item("Transport", 10_000, 8_500, "near"),
            month_spend=20_500,
        ),
        bills=bills([collision("2026-03-12", "2026-03-18", 67_600, ["Phone", "Rent"])], [inc]),
        insights=insights([mover]),
        limits=[limit("atome", 150_000, 140_000)],
    )


def test_recommendations_are_ranked_by_the_fixed_rule_order():
    recs = recommend(everything())
    assert [r.rule for r in recs] == [
        "forecast_shortfall",
        "budget_over",
        "bill_collision",
        "budget_near",
        "plan_near_limit",
        "bill_increase",
        "spending_up",
    ]
    assert [r.priority for r in recs] == sorted(r.priority for r in recs)
    assert [a.rule for a in alerts(everything())] == [
        "forecast_shortfall",
        "budget_over",
        "bill_collision",
    ]


def test_every_rule_is_listed_as_checked():
    assert len(RULES) == 9


NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def test_every_figure_in_every_sentence_comes_from_its_sources():
    for rec in recommend(everything()) + recommend(
        base(forecast=forecast(status="locked", months=2))
    ):
        shown = " ".join(format_source(s) for s in rec.sources)
        allowed = set(NUMBER.findall(shown))
        text = f"{rec.title} {rec.detail} {rec.action.label if rec.action else ''}"
        for figure in NUMBER.findall(text):
            assert figure in allowed, f"{rec.rule}: {figure!r} is not in its sources ({shown})"
        assert rec.sources or rec.rule == "no_budgets"


@pytest.mark.parametrize(
    ("ratio", "text"),
    [(0.465, "47%"), (0.464, "46%"), (0.475, "48%"), (0.005, "1%"), (0.0, "0%"), (1.0, "100%")],
)
def test_a_percentage_rounds_half_up_like_the_screens_do(ratio, text):
    # Local run: the forecast's shortfall chance was exactly 0.465. Python's round() takes half to
    # even ("46%") while the dashboard's Math.round shows "47%", so one page said both.
    from app.domain.recommendations import _pct

    assert _pct(ratio) == text
