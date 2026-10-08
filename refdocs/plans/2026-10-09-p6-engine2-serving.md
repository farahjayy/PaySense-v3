# Plan — P6 Engine 2 serving

> Phase P6 of `refdocs/paysense-v2-PRD.md` §6. Execution doc: `refdocs/execution/2026-10-09-p6-engine2-serving.md`.
> A plan says **what and why**. The execution doc says **how and in what order**.

## Why this exists

P5 produces a trained, calibrated classifier. P6 turns it into the thing a student uses: **"I'm thinking of buying this on SPayLater / TikTok PayLater / Atome. Is it safe, why, and what would make it safer?"** The answer must be a probability and a band, a short plain-language list of the reasons that is *checked against the numbers*, the smallest change that would reach Safe, a chart that shows the margin with and without the purchase, and a separate honest note about the student's repayment history. It is then frozen as a report if the student goes ahead and creates the plan.

The design is fixed in PRD §3.1 and the ADRs: SHAP top factors at or above 0.02 mapped to number-checked templates (D-12), an exact grid search over actionable levers for the counterfactual (D-12), repayment history as a rule-based flag and never a model input (D-11), the displayed probability from the model and the margin chart from the simulation, with their difference logged per check (PRD §3.1 "Displayed versus simulated"), and the server refusing to start if the model's feature hash differs from `features.py` (D-09).

## What changes because of P4/P5 (read their reports first)

- Every number on screen must trace to the model, the simulation or the user's data. The chart is the **simulation** (the same function that produced the training labels); the headline probability is the **calibrated model**. They can disagree; both are shown, and the gap is logged.
- Engine 1's bands are narrower than nominal on short histories (`reports/engine1/serving_check.md`), so the interface says "estimate" and shows the data-quality warnings (stale ledger, suspect months, unmatched confirmed items, `fallback` bootstrap) next to the result instead of hiding them.
- The model was trained on synthetic students. The model card (P7) says so, and the check reports `model_version`, the training-data label version and the feature hash.
- **Author-committed behaviour checks** (academic-constraints §5): "high savings + small purchase → low risk" and "forecast goes negative + large purchase → high risk". Savings are deliberately not credited (D-27), so the first is exercised as *a consistent income surplus in the ledger + small purchase*; this reinterpretation is flagged to the author rather than silently chosen.

## Scope

**In:**
- **Artefact loading** (`app/engines/risk/artefact.py`): load the P5 model and calibrator for the winning model family, verify `FEATURE_SCHEMA_HASH` and the training metadata, refuse to start the API on a mismatch (tested), expose `model_version`.
- **The risk check** (`app/engines/risk/check.py`): ledger + proposed plan (provider, price, instalment count, first payment date, optional manual total for "Other provider") → `propose_plan` (so the limit split and Atome rule apply) → both simulations → features → calibrated `p` → band → `p_simulated` → the gap.
- **Factors** (`explain.py`): SHAP values for the served model family (TreeSHAP for the trees, exact contributions for logistic), top positive contributions ≥ 0.02 mapped to plain-language templates whose numbers are **checked against the feature values** by a test that fails if a template states a number the features do not support; "nothing stands out" is allowed.
- **Counterfactuals** (`counterfactual.py`): an exact grid search over the levers the student controls (a different instalment count the provider offers, a first payment after the next income date, a price 10 / 25 / 50% lower, another provider), re-running the **whole pipeline** for each combination, returning the smallest change that reaches Safe, or "no single change gets there" honestly.
- **Repayment-history flag** (`repayment.py`): overdue instalments in the last six months from the user's own plans, with BNM's three-consecutive-misses suspension rule cited. Separate from the probability.
- **Endpoints**: `POST /api/risk/check` (stateless preview, nothing saved), `POST /api/risk/confirm` (creates the plan through the existing plan service and freezes the check as a `risk_checks` row linked to it), `GET /api/risk/checks/{id}` (the frozen report). Money in integer sen, every query user-scoped, an isolation test per route.
- **Logging** of `p` against `p_simulated` per check for the evaluation chapter.

**Out (and why):**
- Frontend screens (P7).
- Retraining or changing the model (P5). If P6 shows the model misbehaves on a designed case, that is a P5 finding, recorded as such.
- Any lever outside the four above, and any attempt to tell the student what to buy.

## Approach

1. Loader and the hash guard first, with a deliberately mismatched artefact in a test.
2. The check function with a stub model, so the pipeline, the band, the gap and the freezing logic are tested without the real artefact; then the real artefact.
3. SHAP and the templates, with the number-checking test written before the templates.
4. Counterfactual search against the full pipeline (it is the slow part: a latency budget is stated up front).
5. Repayment flag, endpoints, isolation and unauthenticated tests; regenerate the TypeScript client.
6. The designed cases end to end, then latency and memory.

## Risks & unknowns

| Risk / unknown | Confidence | Mitigation |
|---|---|---|
| SHAP is heavy to import and slow per request | Medium | Lazy import on the risk path only; cost measured; TreeSHAP on a small model is milliseconds, the import is the cost |
| Counterfactual grid re-runs the pipeline dozens of times | High | A grid of at most ~60 combinations at ~12 ms each; stop early at the first Safe in order of how much the student must change; latency measured |
| A template states a number the model did not use | Medium | Number-checked templates with a failing test; "nothing stands out" when no factor reaches 0.02 |
| The model and the simulation disagree in a way the student can see | Medium | Both shown; the gap logged; a disagreement threshold produces a visible note rather than a hidden fix |
| The API process grows past the memory budget with SHAP and XGBoost/LightGBM | Medium | Measure; lazy imports; Cloud Run fallback (D-15) recorded as an ADR if needed |
| Freezing a check that referenced data later edited | Low | The row stores inputs, features, outputs and versions, not references |
| A user abuses the stateless check as a free compute service | Medium | Per-user rate limit on the check route (new, tested) |

## Definition of done

- `cd backend && uv run pytest` passes with new tests for the loader (including the hash guard), the check, the explanations (number-checked), the counterfactual search, the repayment flag and every route (unauthenticated, two-user isolation, validation).
- The author-committed behaviour checks pass with the real model, and the reinterpretation of "high savings" is recorded.
- The API refuses to start with a mismatched artefact (tested), and `p` versus `p_simulated` is logged per check.
- A frozen report can be read back identically after the underlying ledger changes.
- Latency of a check including counterfactuals and memory with the model and SHAP loaded are measured and recorded; the Cloud Run fallback is recorded if memory exceeds the budget.
- `ml-auditor`, `fastapi-reviewer`, `security-reviewer` and `python-reviewer` have reviewed; findings fixed or listed in STATUS.
