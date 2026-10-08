# Execution — P6 Engine 2 serving

> Plan: `refdocs/plans/2026-10-09-p6-engine2-serving.md`. Tasks run top to bottom. Each task carries its own **Verify** step; a task is not done until its Verify actually passes.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4).

## Before starting

- Read `CLAUDE.md`, `.claude/memory/preflight.md`, `refdocs/STATUS.md`, PRD §3.1 and §3.2, ADRs D-09, D-11, D-12, D-28, D-33, D-34, D-35, the P5 report (`reports/engine2/README.md`, which model won and how it was calibrated) and `reports/engine1/serving_check.md`.
- New code under `backend/app/engines/risk/` and `backend/app/api/risk.py`. `app/` never imports `ml/` and never imports torch. SHAP is imported lazily, on the risk path only.
- **Stated before building:** counterfactual search stays within a grid of at most 60 combinations and a p95 latency of 3 s for a full check including counterfactuals; API process memory with the model and SHAP loaded stays at or under 450 MB (else record the Cloud Run fallback as an ADR); a factor is shown only if its absolute SHAP value is at least 0.02.
- Money is integer sen at the API boundary (D-29). Every query is user-scoped (D-03).

---

### Task E1 — Artefact loader and the feature-hash guard
- **Files:** `app/engines/risk/artefact.py`, `tests/engines/test_artefact.py`, `app/main.py` (start-up check), `ml/engine2_train/export.py`, `backend/models/engine2/<version>/`.
- **Steps:** export the P5 winner and calibrator (no pickle: native JSON / text formats, or plain arrays for the logistic and forest cases) with `metadata.json` (training data version, feature list and hash, library versions, metrics, CV summary, calibration, git commit, label version). `load_engine2()` verifies the hash and the feature order and returns a `Predictor` (`predict(vector) -> p`, with the calibrator applied). `create_app` calls it when an artefact exists and refuses to start otherwise.
- **Verify:** a test builds an artefact copy whose hash differs and asserts the loader and the app factory refuse it; the real artefact predicts the same values as the in-process model to 1e-6 on 200 held-out vectors.

### Task E2 — The risk check
- **Files:** `app/engines/risk/check.py`, tests.
- **Steps:** `run_check(rows, items, plans, limits, request, today, forecaster, predictor, paths, seed)` → `propose_plan` with the recorded limit → `build_feature_inputs` (both simulations) → features → calibrated `p`, band (pre-registered thresholds), `p_simulated`, `gap`, the simulation curves for the chart (with and without), data-quality warnings from Engine 1, and versions. A locked ledger returns a typed refusal, never a number.
- **Verify:** `uv run pytest tests/engines/test_check.py` — a stub predictor proves the plumbing; a purchase never lowers `p_simulated`; the check is deterministic.

### Task E3 — Factors with number-checked templates
- **Files:** `app/engines/risk/explain.py`, `templates.py`, tests.
- **Steps:** SHAP contributions (lazy import) for the served family; take positive contributions ≥ 0.02, largest first, at most five; one template per feature, each rendering numbers from the feature values (ringgit, percentages, months) and never from anywhere else. "Nothing stands out" when none qualifies.
- **Verify:** the number-checking test extracts every number a rendered sentence contains and asserts it equals a function of the feature values; a sentence can never mention a feature that did not pass the threshold.

### Task E4 — Counterfactual search
- **Files:** `app/engines/risk/counterfactual.py`, tests.
- **Steps:** levers: another instalment count the provider offers, a first payment after the next income date, a price 10 / 25 / 50% lower, another provider; every combination re-runs the whole pipeline (`propose_plan` → simulations → features → calibrated p); return the combination with the smallest change that reaches Safe (change measured as a fixed, documented ordering of effort), or an honest "no single change reaches Safe" with the best achieved.
- **Verify:** tests on constructed ledgers where the answer is known (a longer plan makes an unaffordable purchase Safe; a price cut is chosen when instalments are fixed; nothing reaches Safe on zero income); the grid is capped; latency measured.

### Task E5 — Repayment-history flag
- **Files:** `app/engines/risk/repayment.py`, tests.
- **Steps:** from the user's plans: instalments overdue today and instalments paid late in the last six months; the three-consecutive-misses rule from BNM's personal-financing policy stated as the reason for the warning level; no probability, no model.
- **Verify:** hand-built plan histories give the exact flag.

### Task E6 — Endpoints
- **Files:** `app/api/risk.py`, `app/main.py`, `tests/api/test_risk_api.py`, regenerated `frontend/lib/api/schema.d.ts`; migration edits for `risk_checks` if the frozen shape needs them.
- **Steps:** `POST /api/risk/check` (stateless), `POST /api/risk/confirm` (create the plan via the existing plan service, then freeze the check linked to it; ordering and compensation as in D-30), `GET /api/risk/checks/{id}`; per-user rate limit on the check route; response schemas with bounded floats and integer sen.
- **Verify:** unauthenticated 401, validation 422 envelopes, two-user isolation, a frozen report read back unchanged after the ledger changes, confirm creates exactly one plan and one frozen check, a failure in the middle leaves neither.

### Task E7 — Designed cases and logging
- **Steps:** the author's cases through the whole API with the real model: RM600 over three months is Safe on RM2,000 income, At Risk on RM500 and with no income; a consistent surplus + small purchase is low risk; a negative forecast + a large purchase is high risk; log `p` and `p_simulated` per check and report their gap over 200 synthetic checks.
- **Verify:** tests plus a generated `reports/engine2/serving_check.md`.

### Task E8 — Measurements and reviews
- **Steps:** p50 / p95 latency of a full check including counterfactuals; API process memory with everything loaded; then `ml-auditor`, `fastapi-reviewer`, `security-reviewer`, `python-reviewer`; fix or list.

---

## Wrap-up (do not skip)

- [ ] `refdocs/STATUS.md` — phase table, verification ledger (latency, memory)
- [ ] `refdocs/changelog/CHANGELOG.md` — session entry
- [ ] `refdocs/changelog/DECISIONS.md` — any new ADR (rate limit, artefact format, fallback); PRD §7 one-liners
- [ ] This doc updated to match what actually happened
- [ ] The "high savings" reinterpretation flagged to the author
- [ ] Next: P7 frontend plan and execution docs
