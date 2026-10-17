"""Serving check (plan P6, tasks E7 and E8): `python -m ml.engine2_train.serving_check`.

Runs the exact assessment the API runs (check, reasons, smallest change) on fresh synthetic
students, drawn with a seed no training label used, and reports:

* the gap between the number shown (the model) and the direct simulation of the same purchase,
  and how often they put the student in the same band;
* how often a non-Safe result comes with a change that reaches Safe;
* how long a full assessment takes (with the real forecast network and the real risk model).

Nothing here touches the lockbox: these are different profiles, so the lockbox's one scoring stays
one. The report is written to `reports/engine2/serving_check.md` and regenerates from the command.
"""

# ruff: noqa: E501  (the markdown template below has long table rows)

import argparse
import json
import statistics
import time
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from app.domain.plan_builder import ProposalError
from app.domain.providers import get_provider
from app.engines.forecasting.serving import served_forecaster
from app.engines.forecasting.simulate import SAFE_BELOW, band
from app.engines.risk.artefact import MODEL_ROOT, load_engine2
from app.engines.risk.assess import assess
from app.engines.risk.check import Predictor, RiskRequest, run_check
from app.engines.risk.counterfactual import MAX_EVALUATIONS
from ml.datagen.params import load_params
from ml.datagen.profile import generate_dated_profile
from ml.engine2_train.labels import prepare, profile_seed

REPORT_DIR = Path(__file__).resolve().parents[3] / "reports" / "engine2"
SERVING_SEED = 90001  # no training label used this seed
DEFAULT_PROFILES = 200


def request_for(known: dict[str, Any]) -> RiskRequest:
    """What a student would type: a price for a rule-driven provider, the checkout's own total
    and first payment date for any other provider."""
    proposal = known["proposal"]
    if not get_provider(proposal.provider).rule_driven:
        return RiskRequest(
            provider=proposal.provider,
            item_name="Purchase",
            purchase_date=proposal.purchase_date,
            num_installments=proposal.num_installments,
            first_payment_date=proposal.first_payment_date,
            provider_label=proposal.provider_label,
            total_payable_sen=proposal.total_payable_sen,
        )
    return RiskRequest(
        provider=proposal.provider,
        item_name="Purchase",
        purchase_date=proposal.purchase_date,
        num_installments=proposal.num_installments,
        total_price_sen=proposal.total_price_sen,
        monthly_fee_rate_pct=float(proposal.monthly_fee_rate_pct),
    )


def run(predictor: Predictor, profiles: int = DEFAULT_PROFILES) -> dict[str, Any]:
    params = load_params()
    forecaster = served_forecaster()
    rows: list[dict[str, Any]] = []
    locked = 0
    rejected: Counter[str] = Counter()
    for index in range(profiles):
        profile = generate_dated_profile(params, SERVING_SEED, index)
        known = prepare(profile)
        started = time.perf_counter()
        try:
            found = assess(
                known["rows"], known["items"], known["plans"], known["limits"],
                request_for(known), known["as_of"], forecaster, predictor,
                seed=profile_seed(SERVING_SEED, index),
                savings_buffer_sen=known["savings_buffer_sen"],
            )  # fmt: skip
        except ProposalError as err:
            rejected[err.code] += 1
            continue
        elapsed = time.perf_counter() - started
        if found.result.status != "ok":
            locked += 1
            continue
        suggestion = found.suggestion
        best = suggestion.best if suggestion and suggestion.reaches_safe else None
        suggested_simulated = None
        if best is not None and best.changes:
            checked = run_check(
                known["rows"], known["items"], known["plans"], known["limits"], best.request,
                known["as_of"], forecaster, predictor, seed=profile_seed(SERVING_SEED, index),
                savings_buffer_sen=known["savings_buffer_sen"],
            )  # fmt: skip
            suggested_simulated = checked.p_simulated
        rows.append(
            {
                "index": index,
                "p": found.result.probability,
                "p_simulated": found.result.p_simulated,
                "band": found.result.band,
                "band_simulated": band(found.result.p_simulated),
                "seconds": elapsed,
                "factors": len(found.factors),
                "suggestion_found": bool(suggestion and suggestion.reaches_safe)
                and found.result.band != "Safe",
                "needed_suggestion": found.result.band != "Safe",
                "evaluated": suggestion.evaluated if suggestion else 0,
                "p_without": found.result.p_without,
                "suggested_simulated": suggested_simulated,
                "suggestion_basis": best.basis if best is not None else None,
            }
        )
    return summarise(rows, profiles, locked, rejected)


def summarise(
    rows: list[dict[str, Any]], profiles: int, locked: int, rejected: Counter[str]
) -> dict[str, Any]:
    if not rows:
        raise ValueError("no profile could be assessed, so there is nothing to report")
    gap = np.array([r["p"] - r["p_simulated"] for r in rows])
    seconds = np.array([r["seconds"] for r in rows])
    needed = [r for r in rows if r["needed_suggestion"]]
    return {
        "profiles": profiles,
        "assessed": len(rows),
        "locked": locked,
        "rejected_by_plan_rules": sum(rejected.values()),
        "rejected_reasons": dict(rejected),
        "gap": {
            "mean": float(gap.mean()),
            "mean_abs": float(np.abs(gap).mean()),
            "p95_abs": float(np.quantile(np.abs(gap), 0.95)),
            "max_abs": float(np.abs(gap).max()),
        },
        "band_agreement": float(np.mean([r["band"] == r["band_simulated"] for r in rows])),
        "non_safe": len(needed),
        "non_safe_short_before_purchase": _share(needed, lambda r: r["p_without"] >= SAFE_BELOW),
        "band_agreement_where_plan_decides": _share(
            [r for r in rows if r["p_without"] < SAFE_BELOW],
            lambda r: r["band"] == r["band_simulated"],
        ),
        "plan_decides_profiles": sum(1 for r in rows if r["p_without"] < SAFE_BELOW),
        "suggestion_safe_by_simulation": _share(
            [r for r in rows if r["suggested_simulated"] is not None],
            lambda r: r["suggested_simulated"] < SAFE_BELOW,
        ),
        "suggestions_checked": sum(1 for r in rows if r["suggested_simulated"] is not None),
        "suggestion_basis": dict(
            Counter(r["suggestion_basis"] for r in rows if r["suggested_simulated"] is not None)
        ),
        "non_safe_with_no_reason": _share(needed, lambda r: r["factors"] == 0),
        "suggestion_reaches_safe": float(np.mean([r["suggestion_found"] for r in needed]))
        if needed
        else None,
        "mean_evaluations_when_not_safe": float(statistics.fmean(r["evaluated"] for r in needed))
        if needed
        else None,
        "mean_factors_shown": float(np.mean([r["factors"] for r in rows])),
        "share_with_no_factor": float(np.mean([r["factors"] == 0 for r in rows])),
        "slowest": [
            {"index": r["index"], "seconds": round(r["seconds"], 3)}
            for r in sorted(rows, key=lambda r: r["seconds"], reverse=True)[:5]
        ],
        "seconds": {
            "p50": float(np.quantile(seconds, 0.5)),
            "p95": float(np.quantile(seconds, 0.95)),
            "max": float(seconds.max()),
        },
    }


def _share(items: list[dict[str, Any]], test: Callable[[dict[str, Any]], bool]) -> float | None:
    return float(np.mean([bool(test(i)) for i in items])) if items else None


def render(result: dict[str, Any], predictor: Predictor) -> str:
    gap, secs = result["gap"], result["seconds"]
    tried = result["mean_evaluations_when_not_safe"] or 0
    basis = ", ".join(f"{k}: {v}" for k, v in result["suggestion_basis"].items()) or "none"
    reasons = ", ".join(f"{k}: {v}" for k, v in result["rejected_reasons"].items()) or "none"

    def pct(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.1%}"

    safe_pct = f"{SAFE_BELOW:.0%}"
    return f"""# Engine 2 serving check

> Generated by `python -m ml.engine2_train.serving_check` - do not edit by hand.

The risk check as the API runs it (check, reasons, smallest change), with the real forecast
network and the served model `{predictor.version}`, on {result["profiles"]} fresh synthetic
students (seed {SERVING_SEED}; no training label and not the lockbox).
{result["assessed"]} were assessed; {result["locked"]} were locked (too little history) and
{result["rejected_by_plan_rules"]} were rejected by the plan rules ({reasons}).

## The number shown against the direct simulation

| measure | value |
|---|---|
| mean of (model - simulation) | {gap["mean"]:+.4f} |
| mean absolute gap | {gap["mean_abs"]:.4f} |
| 95th percentile of the absolute gap | {gap["p95_abs"]:.4f} |
| largest absolute gap | {gap["max_abs"]:.4f} |
| same band | {pct(result["band_agreement"])} |
| same band, students not already short before the purchase ({result["plan_decides_profiles"]}) | {pct(result["band_agreement_where_plan_decides"])} |

## What a student gets

| measure | value |
|---|---|
| results not Safe | {result["non_safe"]} |
| of those, already short before the purchase (simulated chance of {safe_pct} or more without it) | {pct(result["non_safe_short_before_purchase"])} |
| of those, a change that reaches Safe was found | {pct(result["suggestion_reaches_safe"])} |
| of the changes found, Safe by the direct simulation too ({result["suggestions_checked"]} checked) | {pct(result["suggestion_safe_by_simulation"])} |
| how the changes found were judged | {basis} |
| combinations tried when not Safe (mean, cap {MAX_EVALUATIONS}) | {tried:.1f} |
| reasons shown (mean) | {result["mean_factors_shown"]:.2f} |
| results with no reason ("nothing stands out"), all results | {pct(result["share_with_no_factor"])} |
| results with no reason, results that are not Safe | {pct(result["non_safe_with_no_reason"])} |

## Time for a full assessment

Single process, one request at a time, on the machine that made this report.

| p50 | p95 | max |
|---|---|---|
| {secs["p50"]:.2f} s | {secs["p95"]:.2f} s | {secs["max"]:.2f} s |

The ledgers here come from the generator through the same detection the labels used, not from the database path (24-month window, confirmed items); the engine is the same. The target was a p95 of 3 s. Slowest five (profile index, seconds):
{", ".join(f"{s['index']}: {s['seconds']:.2f}" for s in result["slowest"])}.
"""


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serving check for the Engine 2 artefact.")
    parser.add_argument("--profiles", type=int, default=DEFAULT_PROFILES)
    parser.add_argument("--model", type=Path, default=MODEL_ROOT / "v2")
    parser.add_argument("--out", type=Path, default=REPORT_DIR)
    args = parser.parse_args(argv)
    predictor = load_engine2(args.model)
    result = run(predictor, args.profiles)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "serving_check.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (args.out / "serving_check.md").write_text(
        render(result, predictor), encoding="utf-8", newline="\n"
    )
    print(render(result, predictor))  # noqa: T201


if __name__ == "__main__":
    main()
