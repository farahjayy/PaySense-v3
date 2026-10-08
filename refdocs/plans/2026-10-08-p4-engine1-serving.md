# Plan — P4 Engine 1 serving

> Phase P4 of `refdocs/paysense-v2-PRD.md` §6. Execution doc: `refdocs/execution/2026-10-08-p4-engine1-serving.md`.
> A plan says **what and why**. The execution doc says **how and in what order**.

## Why this exists

P3 answered *which forecaster*. P4 turns it into the product: given a user's ledger, produce the forecast the dashboard shows and the simulation Engine 2 will later be trained on and asked about. The design is fixed in PRD §3.1 (decided design) and D-27 / D-28: **known flows** (confirmed recurring income and bills, every unpaid BNPL instalment, the checkout payment of a plan under evaluation) are placed on their exact dates; **two variable weekly series** (discretionary spend, and income that is not a confirmed recurring item) are forecast by the P3 winner; a **residual bootstrap** gives uncertainty; a **Monte Carlo of the monthly margin** gives P10/P50/P90 and **P(shortfall)**. There is no balance anywhere.

This phase also carries the behaviours the author described in her design concern, which are acceptance tests, not nice-to-haves: a RM600 purchase over 3 months is **Safe** on RM2,000 monthly income, **At Risk** on RM500 monthly income, and **At Risk** with savings only and no income.

## What changes because of the P3 result (read the P3 README first)

- The served model is whatever the D-06 rule picked in `reports/engine1/selection.json`. The plan covers every branch: a benchmark (no new dependency), Prophet or AutoARIMA (needs `prophet` / `statsforecast` in the API process, which the P0 spike measured at about 15 MB / a few hundred MB with numba, and which today's import guard in `tests/ml/test_boundaries.py` forbids), or the LSTM (exported to ONNX and served with `onnxruntime`; torch must never enter the API process, D-15).
- If the winner is not on the guard's allow-list, amending the guard is an ADR and is stated in STATUS.
- P3 flagged (ASSUMED 9) that MASE can favour a model that is biased on the running total. P4 therefore **measures the served model's signed level bias on the user-shaped cohort and on the real datasets, and the Monte Carlo re-centres each simulated path on the model's own past signed errors**; the designed-case tests below are the product-level check that the combination is not biased in a way that matters.

## Scope

**In:**
- **Recurring detection** (suggest only; the user confirms): merchant normalisation → group → dominant inter-arrival gap (7 / 14 / 28–31 days) → amount within ±15% → at least three occurrences. Pure function over the ledger; a new stateless endpoint returns suggestions; confirming goes through the existing recurring-items routes (`origin = detected`). Scored against the generator's `recurring_truth` (precision / recall) in a test, not by eye.
- **Variable series builder**: weekly Monday–Sunday sums of (a) expenses not linked to a recurring item or BNPL plan, not `savings`, not transfers, refunds netted; (b) income not covered by a confirmed recurring income. The current incomplete week is excluded. Weeks straddling a month are split by days when placed in months.
- **Completeness and the 4-month gate**: fewer than four months of history locks the forecast (supervisor constraint). Months that look incomplete (no income logged although income occurs in other months; spend far below the user's typical) are listed with a warning; the forecast is still produced and the noisy months stay in the residuals so the bands widen. Thresholds are set here (ASSUMED 6, 10), written down as an ADR, and tested on the synthetic personas with deliberately incomplete months.
- **Served model + residual bootstrap**: the P3 winner behind the same interface; the user's own rolling-origin errors resampled in 4-week blocks, 1,000 paths, seeded so a request is reproducible.
- **Monthly-margin Monte Carlo**: per path and month, `income − bills − BNPL instalments (incl. checkout payments) − discretionary`; cumulative margin from RM0; P10/P50/P90 monthly and cumulative; **P(shortfall)** = share of paths whose cumulative margin is below RM0 at any month-end of the horizon; the month most likely to go negative. A function `simulate(ledger, plans, proposed_plan=None, horizon)` is the single entry point P5 (labels) and P6 (risk check) call.
- **`GET /api/forecast`**: the dashboard's three-month forecast, health score `round((1 − P(shortfall, no new purchase)) × 100)` with the Safe / Caution / At Risk bands, completeness warnings. Money in integer sen at the boundary (D-29); every query user-scoped (D-03) with an isolation test.
- **Measurements**: forecast latency (target stated in the execution doc) and process memory with the served model loaded, recorded for the Render-versus-Cloud-Run decision (D-15).

**Out (and why):**
- The Engine 2 feature file, labels and any classifier (P5/P6). P4 only provides `simulate`.
- Frontend screens (P7). The API contract is generated; the dashboard consumes it later.
- Savings credit / a balance input (D-27 limitation, future work).
- Any model outside D-05.

## Approach

1. Pure functions first, each with tests on hand-built ledgers: recurring detection, series builder, month placement of known flows, completeness.
2. The simulation core with a *fake* constant forecaster, so the designed cases (RM2,000 / RM500 / savings-only) pin down the margin and shortfall logic independently of any model.
3. Plug in the served model and the residual bootstrap; re-run the designed cases with the real model; measure bias on the cohort.
4. The endpoint, with the 4-month gate, warnings and isolation tests.
5. Performance measurements last, on the real stack, and recorded.

## Risks & unknowns

| Risk / unknown | Confidence | Mitigation |
|---|---|---|
| The winner needs a heavy dependency in the API process | Medium | Decide from `selection.json`; measure RSS with the real model; Cloud Run at 1 GiB is the documented fallback (D-15) |
| The served model's level bias distorts P(shortfall) | Medium | Bias is measured and the paths are re-centred on signed past errors; designed-case tests; a sensitivity run with the bias term removed is reported |
| Recurring detection mislabels a variable merchant as a bill | High | It only suggests; precision/recall against the generator's ground truth; the user confirms |
| Short user histories (17+ weeks) give few residuals | High | Block bootstrap falls back to a plain residual bootstrap with a visible note; bands widen rather than the number becoming falsely precise |
| 1,000 paths × 52 weeks is slow in pure Python | Low | Vectorised numpy; latency target measured |
| Incomplete months make a user look At Risk unfairly | Medium | Completeness warnings; thresholds tested; the UI (P7) shows the warning next to the number |

## Definition of done

- `cd backend && uv run pytest` passes with new tests for each pure function and each route; coverage on `app/engines/forecasting` ≥ 80%.
- The designed cases pass with the real served model: RM600 over 3 months → Safe at RM2,000 monthly income, At Risk at RM500, At Risk with savings only; plus PTPTN lump-sum timing, a bill landing on the same day as an instalment, and stacked instalments from several providers.
- Recurring detection reaches its precision/recall floor against the generator's ground truth (floor stated in the execution doc before measuring).
- `GET /api/forecast` returns the contract, is locked behind the 4-month gate, and has an unauthenticated test and a two-user isolation test.
- Latency and memory with the served model loaded are recorded in STATUS; if memory exceeds ~450 MB the Cloud Run fallback is recorded as an ADR.
- `ml-auditor`, `python-reviewer`, `fastapi-reviewer` and `security-reviewer` have reviewed; findings fixed or listed in STATUS.
