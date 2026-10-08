# Execution — P4 Engine 1 serving

> Plan: `refdocs/plans/2026-10-08-p4-engine1-serving.md`. Tasks run top to bottom. Each task carries its own **Verify** step; a task is not done until its Verify actually passes.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4).

## Before starting

- Read `CLAUDE.md`, `.claude/memory/preflight.md`, `refdocs/STATUS.md`, PRD §3.1, ADRs D-03, D-04, D-06, D-15, D-27, D-28, D-29, D-31, `reports/engine1/README.md` and `selection.json` (which model was served and why), and `reports/datagen/README.md`.
- Code lives under `backend/app/engines/forecasting/` and `backend/app/api/forecast.py`. `app/` must never import `ml/`. Torch must never be imported in `app/` (D-15).
- **Targets stated before measuring** (so they cannot be tuned afterwards): recurring detection precision ≥ 0.85 and recall ≥ 0.75 on the synthetic personas' `recurring_truth`; `GET /api/forecast` p95 latency ≤ 1.5 s for a 3-month horizon on the development machine; API process memory with the served model loaded ≤ 450 MB (otherwise record the Cloud Run fallback as an ADR).
- Money is integer sen inside the engine; convert at the API boundary only (D-16, D-29).

---

### Task C1 — Recurring detection
- **Files:** `app/engines/forecasting/recurring.py`, `tests/engines/test_recurring_detection.py`.
- **Steps:** merchant-text normalisation (digits, card suffixes and dates stripped), grouping, dominant inter-arrival gap among 7 / 14 / 28–31 days with low variance, amount within ±15% of the group's median, at least three occurrences. Output `Suggestion(name, kind, amount_sen, cadence, anchor_date, confidence, occurrences)`. Never writes anything. Tests: hand-built ledgers (a monthly rent, a weekly allowance, a variable merchant that must **not** be suggested, a refund that must not count, two-occurrence items that must not be suggested); then a precision/recall test against `ml.datagen` personas' `recurring_truth` is allowed **only in a test** (the test may import `ml`; `app/` may not).
- **Verify:** `uv run pytest tests/engines/test_recurring_detection.py`; the measured precision and recall are written into the changelog next to the stated floor.

### Task C2 — Variable weekly series
- **Files:** `app/engines/forecasting/series.py`, tests.
- **Steps:** build the discretionary and unconfirmed-income weekly series from ledger rows using `domain.flows.classify` (refunds net against spend, transfers excluded), excluding transactions linked to a recurring item or BNPL plan and `savings`; complete Monday–Sunday weeks only; zero-filled gaps; the current incomplete week excluded. Month placement of a week splits by days.
- **Verify:** `uv run pytest tests/engines/test_series.py` — a ledger with a known refund, a transfer, a BNPL payment and a confirmed bill gives the exact expected weekly sums.

### Task C3 — Completeness and the 4-month gate
- **Files:** `app/engines/forecasting/completeness.py`, tests, ADR in `DECISIONS.md`.
- **Steps:** fewer than four calendar months of history ⇒ `locked`. Incomplete-month rules (no income logged although income occurs in other months; spend below a fraction of the user's median month) with thresholds chosen on the synthetic personas with deliberately blanked months, recorded as an ADR and as a test fixture. Returns the list of suspect months with a reason each.
- **Verify:** `uv run pytest tests/engines/test_completeness.py`; ASSUMED 6 and 10 are resolved or restated.

### Task C4 — Known flows placed on dates
- **Files:** `app/engines/forecasting/flows.py`, tests.
- **Steps:** expand confirmed recurring items by cadence, plans' unpaid instalments (D-28: a plan under evaluation adds its checkout payment in the purchase month), future-dated savings goals; each into the calendar month of its exact date; the horizon cut-off handled explicitly.
- **Verify:** `uv run pytest tests/engines/test_flows.py` — a PTPTN lump sum, a bill on the same day as an instalment, and a 31st-of-month bill in February each land in the right month.

### Task C5 — The simulation core (with a fake forecaster)
- **Files:** `app/engines/forecasting/simulate.py`, `margin.py`, tests.
- **Steps:** `simulate(series, known_flows, forecaster, residuals, proposed_plan, horizon, paths, seed) -> Simulation` with monthly and cumulative P10/P50/P90, `p_shortfall`, `worst_month`. Vectorised numpy. Re-centres each path on the model's own past signed errors (the P3 bias point). Deterministic under the seed.
- **Verify:** with a constant fake forecaster the **designed cases** pass: RM600 over 3 months on RM2,000 monthly income ⇒ P(shortfall) < 0.10 (Safe); on RM500 ⇒ ≥ 0.30 (At Risk); with no income and savings only ⇒ ≥ 0.30. Also stacked instalments from three providers, and a plan whose limit forces a checkout payment.

### Task C6 — The served model and the residual bootstrap
- **Files:** `app/engines/forecasting/model.py`, `bootstrap.py`, tests; dependency changes only as the P3 result requires.
- **Steps:** load the winner behind the P3 `Forecaster` interface (benchmark: nothing new; Prophet / AutoARIMA: add the dependency and amend the import guard by ADR; LSTM: export to ONNX in `ml/`, check the ONNX output against torch to a stated tolerance, serve with `onnxruntime`). Rolling-origin errors of this model on the user's own series, resampled in 4-week blocks (plain residual bootstrap with a visible note when fewer than two blocks).
- **Verify:** `uv run pytest tests/engines/`; the designed cases re-run with the real model; a bias report on the synthetic cohort and on MoneyData / Berka (mean signed error of the cumulative margin) is written to `reports/engine1/serving_bias.md` by a script.

### Task C7 — `GET /api/forecast`
- **Files:** `app/api/forecast.py`, `app/main.py` (router), `tests/api/test_forecast_api.py`, regenerated `frontend/lib/api/schema.d.ts`.
- **Steps:** gate (`locked` response below four months), dashboard three-month forecast, health score and band, completeness warnings, money in sen. Every query user-scoped; no route builds a query. Deterministic seed derived from the user id and the as-of date.
- **Verify:** `uv run pytest tests/api/test_forecast_api.py` — unauthenticated 401, two-user isolation, locked state, a happy path from a seeded persona; `cd frontend && npm run gen:api && npm run check:api`.

### Task C8 — Performance measurements
- **Steps:** p50/p95 latency of 100 forecast calls on a seeded persona; process RSS with the served model loaded (`psutil` in a throwaway script, not a dependency). Write both to STATUS. If RSS > 450 MB, record the Cloud Run fallback as an ADR.
- **Verify:** numbers in STATUS compared with the targets above.

### Task C9 — Reviews
- **Steps:** `ml-auditor` (train/serve parity of the series builder, bias handling), `python-reviewer`, `fastapi-reviewer`, `security-reviewer` (new endpoint, user scoping); fix or list.

---

## Wrap-up (do not skip)

- [ ] `refdocs/STATUS.md` — phase table, verification ledger (latency, memory, precision/recall)
- [ ] `refdocs/changelog/CHANGELOG.md` — session entry
- [ ] `refdocs/changelog/DECISIONS.md` — completeness ADR, any dependency / import-guard ADR; PRD §7 one-liners
- [ ] This doc updated to match what actually happened
- [ ] Next: write `refdocs/plans/<date>-p5-engine2-training.md` + its execution doc
