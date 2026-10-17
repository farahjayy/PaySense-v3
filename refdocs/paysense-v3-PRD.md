# PaySense v3 — Product Requirements Document (PRD)

> PaySense is an AI-driven decision support system that helps Malaysian university students make informed Buy Now, Pay Later (BNPL) purchasing decisions. It integrates **financial health forecasting** (projecting the student's monthly margin — income less bills, instalments and spending — with uncertainty, from their own transaction history, known income, bills and existing BNPL instalments; no account balance is needed) with **BNPL risk classification** (scoring a proposed purchase, before commitment, by the probability that the student cannot meet the plan from their income within the plan's horizon), and explains every result in plain language with what would make it safe. v2 is the final FYP product; v1 (`../PaySense/`) was the experiment it learns from.

- **Owner:** Nur Farah Binti Ahmad Nazri (UTP, BSc Computer Science — FYP2). Supervisor: Dr. Nazleeni Samiha Bt Haron.
- **Users:** Malaysian university students who hold a bank (debit/savings) account and e-wallets but typically **no credit card** — BNPL is their main form of credit. In the evaluation build: 5–7 UAT testers on pre-seeded usernames, across 3 personas.
- **Status:** Scaffolded 2026-10-08 — pre-implementation
- **Last updated:** 2026-10-08
- **Source of record:** [paysense-v3-sources.md](paysense-v3-sources.md)
- **Founding context:** [context/v1-lessons.md](context/v1-lessons.md) · [context/research-2026-10-08.md](context/research-2026-10-08.md) · [context/academic-constraints.md](context/academic-constraints.md) · [context/bnpl-billing-rules-my.md](context/bnpl-billing-rules-my.md)

---

## 1. Context & Hard Constraints

Confirmed from the founding context documents and the scaffold interview (2026-10-08).

| Constraint | Value | Consequence |
|---|---|---|
| Public repository | v2 is a **public** GitHub repo from its first commit (examiners and advisors read it) | No real personal financial data, no secrets, ever. Real data lives only in gitignored `data/private/`. |
| Candidate algorithms | Fixed by the FYP literature review: ARIMA / Prophet / LSTM; Random Forest / XGBoost / LightGBM; SHAP | No new candidate algorithms. Benchmarks and model *configurations* are allowed with a methodology citation (D-05). |
| Login | Pre-seeded usernames, no passwords, no sign-up (supervisor decision) | Username-only session login; every row is user-scoped (D-03). |
| Input methods | CSV import + manual entry. PDF parsing and bank integration out of scope (supervisor) | Import path must be excellent; persona CSVs are first-class fixtures. |
| Minimum history | 4 months of transactions before forecast and risk unlock (supervisor) | Explicit locked state in the UI below the threshold — never a degraded fake forecast. |
| No fabricated outputs | Even the contingency path pipes real model outputs from verified data, never invented values (supervisor) | Every number on screen traces to a model, a simulation or the user's data. |
| Hosting | Vercel (frontend) + Render (backend) + Supabase Postgres (supervisor plan) | Backend must fit Render's memory; measure it (D-15). |
| Terminology | "financial health forecasting" and "BNPL risk classification" (supervisor) | Used consistently in UI text, docs and reports. |
| Privacy | PDPA 2024 amendment; synthetic personas by default; Supabase Singapore = cross-border transfer | Derived features only to any third-party API; consent text in the UAT kit. |
| Tooling environment | Windows 11 dev machine; Python 3.14 installed system-wide; Node 24; `uv` installed in P0 | uv pins Python 3.12, the version every dependency supports (D-23, verified by the P0 spike). |

---

## 2. Product Principles

1. **Show the consequence, not a warning.** The decisive screen is *your* projected monthly margin with and without this purchase. Generic disclosures don't change behaviour (research §D).
2. **Place what is known, forecast only what isn't.** Income, bills and instalments have dates and amounts — they are placed exactly. Only discretionary spending is forecast.
3. **Uncertainty is part of the answer.** Bands and probabilities, never one confident line.
4. **Every score explains itself and says what would make it safe.**
5. **The label must not be the author's opinion.** Engine 2 learns from a forward cash-flow simulation, not from a hand-written formula (v1's core failure).
6. **One definition per quantity.** A feature is computed by one function, used by data generation, training and serving alike.
7. **Honest evaluation.** Benchmarks always included; repeated, rolling, statistically tested; results reported even when unflattering.
8. **Traffic-light first, number second, chart third** for every risk output.

---

## 3. Architecture

```
 Browser (Next.js on Vercel)
   │  Authorization: Bearer <session token>      typed client generated from OpenAPI
   ▼
 FastAPI (Render) ─────────────────────────────────────────────────────────────
   │ api/        auth · transactions · imports · recurring · month summary · providers
   │             plans · bills · forecast · risk · dashboard
   │ domain/     ledger maths · schedule (sen maths) · providers + limits · categorize · recurring detection
   │ engines/
   │   forecasting/   (Financial Health Forecasting — "Engine 1")   [no balance anchor — D-27]
   │      known flows ──► placed on exact dates (confirmed income, bills, BNPL instalments, checkout payment)
   │      weekly variable series (discretionary spend; income when not confirmed) ─► served model (winner of P3) ─► residual bootstrap
   │      Monte Carlo (1,000 paths) ─► P10/P50/P90 monthly + cumulative margin, P(shortfall) = cumulative margin < RM0 at a month-end
   │   risk/          (BNPL Risk Classification — "Engine 2")
   │      features.py (THE shared feature module) ◄── forecast outputs + plans + proposal
   │      calibrated classifier (winner of P5) ─► P(shortfall) ─► Safe / Caution / At Risk
   │      SHAP factors + counterfactual search (re-runs the pipeline) + repayment-history flag
   │ db/         repository layer — every query takes user_id
   ▼
 Supabase Postgres (Singapore) — accessed only by the backend (service key); RLS on, no anon policies

 ml/ (offline, same repo, imports engines/ — never the reverse)
   datagen/        synthetic Malaysian-student population → Engine 2 training set, Engine 1 cohort, persona CSVs
   engine1_eval/   rolling-origin comparison of 5 forecasters on 4 datasets → reports/engine1/
   engine2_train/  simulation labels → 4 classifiers, tuning, repeated CV, calibration, ablation → models/ + reports/engine2/
```

**Why sequential (the dissertation's architecture argument):** the risk of a BNPL purchase is a property of the *future* — whether the months ahead leave enough margin, after income, bills and every instalment, to absorb the new plan. Historical aggregates cannot see a PTPTN disbursement landing in one month and not the next, a bill and an instalment stacking in the same month, or a stack of plans from different providers. (Intra-month timing — an instalment due days before the next income — is surfaced as a flag, not part of the label; D-27.) The forecast is therefore not one input among many: it **generates the training label** (simulated shortfall) and supplies the forward-looking features. The ablation in P5 measures exactly how much it contributes.

### 3.1 Components

**Financial health forecasting (Engine 1) — decided design**

| Step | Definition |
|---|---|
| Known flows | Confirmed recurring income (allowance, PTPTN disbursements, part-time pay), confirmed recurring bills, every unpaid BNPL instalment, the checkout payment of a plan under evaluation (D-28), future-dated savings goals. Placed in the month of their exact dates. Recurring items are *suggested* by a detection heuristic (merchant normalisation → dominant gap 7/14/28–31 days → amount within ±15% → ≥3 occurrences) and *confirmed* by the user. |
| Variable series | Weekly (Mon–Sun) sums of (a) expense transactions not linked to a recurring item or BNPL plan and not of type `savings` — discretionary spend — and (b) income transactions not covered by a confirmed recurring income (irregular / gig income). The current, incomplete week is excluded. |
| Forecast | Served model (P3 winner) forecasts each weekly series for the horizon: 3 months on the dashboard; through the last due date of the plan under evaluation for a risk check (bounded at 180 weeks, D-36). Weeks that straddle a month boundary are split by days. |
| Uncertainty | Residual bootstrap: each path resamples the served model's rolling-origin forecast errors (moving-block bootstrap, block = 4 weeks), the same method for every candidate so the comparison is fair. 1,000 paths. |
| Monthly margin | **No starting balance (D-27).** For each month of the horizon, per path: `margin = income − bills − BNPL instalments (incl. checkout payments) − discretionary spend`. Cumulative margin starts at RM0 at the start of the current month ("no savings assumed"; D-33) and accumulates month by month, the current month using its actual net so far plus the simulated remainder. |
| Outputs | P10/P50/P90 monthly and cumulative margin; **P(shortfall)** = share of paths where the cumulative margin at any month-end in the horizon is < RM0, i.e. the plan could not be paid from income alone; the month most likely to go negative. |
| Health score (dashboard) | `round((1 − P(shortfall over next 3 months, no new purchase)) × 100)`, same Safe/Caution/At Risk bands as Engine 2. |
| Gate | Fewer than 4 months of history → locked state with an import prompt (supervisor constraint). |
| Completeness | Months that look incomplete (no income logged although income occurs in other months; spend far below the user's typical) are listed with a warning. The forecast is still produced — the noisy months stay in the residuals, so the bands widen, never a hidden fake-precise number. Thresholds are set in P4 (`ASSUMED`). |

**BNPL risk classification (Engine 2) — decided design**

| Element | Definition |
|---|---|
| Target | `p_shortfall_with`: Engine 1's simulated probability that, **with the proposed plan added** (its checkout payment in the purchase month, its financed instalments on their dates), the cumulative income-minus-outgoings margin at any month-end within the plan's horizon falls below RM0. Precedent: Bijak, Thomas & Mues (dynamic affordability); BNM household financial-margin stress test; CCA 2025 affordability duty. |
| Training data | ~10,000 synthetic student profiles from `ml/datagen` (transaction-level histories + existing plans + one proposed purchase each), every one run through the *served* Engine 1 to produce its label — so training and serving see the same forecaster. |
| Soft labels | Trained as probabilistic classifiers on soft targets by duplicate-and-weight: each profile appears once as class 1 with weight p and once as class 0 with weight 1 − p. Works identically for all four models. |
| Features | Defined only in `engines/risk/features.py` (§3.2 table). Age and employment status are dropped (not needed for affordability; fairness). |
| Candidates | Random Forest, XGBoost, LightGBM — all with **monotonic constraints** on the features whose direction is known — plus a logistic-regression benchmark. |
| Selection | 5×5 repeated stratified CV (strata = p_shortfall deciles), grouped by profile; hyperparameters tuned in an inner loop (Optuna, budget recorded). Primary metric: Brier score against the soft target. Secondary: log-loss, ROC-AUC at p ≥ 0.30, calibration slope and ECE. Pairwise Nadeau–Bengio corrected resampled t-tests (port of v1's harness). |
| Calibration | None / Platt / isotonic chosen by nested CV (port of v1's procedure). |
| Proof of the link | **Ablation:** retrain the winner without the Engine-1-derived features; report ΔBrier with its CI. **Stress test:** income −20% and a delayed PTPTN disbursement. |
| Bands | Safe: p < 0.10 · Caution: 0.10 ≤ p < 0.30 · At Risk: p ≥ 0.30. Pre-registered before training — not tuned on results. Score shown = `round((1 − p) × 100)`. |
| Explanation | SHAP (TreeSHAP for the tree models; exact contributions for the logistic benchmark), top positive factors ≥ 0.02, mapped to plain-language templates whose numbers are checked against the feature values. "Nothing stands out" is allowed. |
| Counterfactuals | "What would make this Safe": re-run the full pipeline over actionable levers — fewer/more instalments the provider offers, first payment after the next income date, a lower price (−10/−25/−50%), another provider — and show the smallest change that reaches Safe. Concept cited to DiCE / Ustun et al.; implemented as an exact grid search. |
| Repayment history | **Not a model feature.** Shown as a separate rule-based flag: overdue instalments in the last 6 months, with BNM's 3-consecutive-misses suspension rule cited. Keeps v1's synthetic-missed-payments distortion out of the model (D-11). |
| Displayed vs simulated | The UI shows the model's calibrated p; the margin chart shows the simulation bands. Their difference is logged per check for the evaluation chapter. |

### 3.2 Data & state

**Postgres tables** (every table except `users` carries `user_id uuid not null references users(id) on delete cascade`):

| Table | Purpose |
|---|---|
| `users` | `id`, `username` (unique, case-insensitive), `display_name`, `persona` (`frequent_bnpl` / `budget_conscious` / `irregular_income` / null), `created_at`. Seeded by an admin script; no sign-up endpoint. |
| `user_settings` | Onboarding state only. **No balance** (D-27): forecasting runs on flows. |
| `transactions` | v1 shape (`date`, `amount` > 0, `type` income/expense/savings, `category`, `description`, `account_name`, `is_bnpl`, `source` manual/csv/seed) + `bnpl_plan_id`, `bnpl_installment_id` (the instalment a logged payment settles; unique, D-30), `recurring_item_id`. Amounts are `amount_sen` (bigint). |
| `recurring_items` | `kind` income/bill, `name`, `amount`, `cadence` weekly/biweekly/monthly/semester/custom, `anchor_date`, `active`, `origin` detected/manual. |
| `bnpl_plans`, `bnpl_installments` | v1 shape (provider, price, monthly fee rate, instalments, first payment date, status, paid flags) + `risk_check_id`, `risk_check_type`. Money in sen. The financed part and the checkout payment are both derivable from the plan (D-28). |
| `provider_limits` | Optional per-user credit limit per provider. It caps how much of a purchase can be financed; the excess is paid at checkout (D-28). |
| `risk_checks` | `input`, `features` (+ `feature_schema_hash`), `model_version`, `p`, `p_simulated`, `label`, `factors`, `counterfactuals`, `curves` — frozen for the per-plan risk report. |

**Engine 2 feature set** (exact definitions live in `features.py`; this is the contract):

| Feature | Source | Monotone direction |
|---|---|---|
| `disc_weekly_p50` — mean forecast weekly discretionary spend over the plan horizon (P50) | Engine 1 | ↑ risk |
| `disc_weekly_p90` — mean P90 weekly discretionary spend over the horizon | Engine 1 | ↑ |
| `disc_volatility` — std of the served model's weekly forecast residuals | Engine 1 | ↑ |
| `margin_monthly_p50_without` — median monthly margin over the horizon, without the purchase (RM) | Engine 1 | ↓ |
| `margin_cum_p10_without` — lowest P10 cumulative margin at any month-end over the horizon, without the purchase (RM) | Engine 1 | ↓ |
| `income_p10_monthly` — P10 of forecast monthly income over the horizon (RM); the downside income the plan must survive | Engine 1 | ↓ |
| `instalment_amount` — financed instalment, after the limit cap (D-28) | Plan | ↑ |
| `num_instalments` | Plan | none |
| `monthly_fee_rate` | Plan | ↑ |
| `instalment_to_income` — proposed instalment / expected monthly income | Plan + known flows | ↑ |
| `dsr_with_purchase` — (all monthly BNPL obligations incl. the new plan + monthly debt-like bills) / expected monthly income | Commitments | ↑ |
| `active_plans_with_purchase` | Commitments | ↑ |
| `bnpl_outstanding_to_income` — total unpaid BNPL incl. the purchase (excluding any part paid at checkout) / monthly income | Commitments | ↑ |
| `upfront_to_income` — amount paid at checkout because the provider limit caps financing (D-28) / expected monthly income; 0 when the purchase fits the limit | Plan + limits | ↑ |
| `limit_utilisation_with_purchase` — (unpaid financed amount on this provider + this plan's financed amount) / provider limit; 0 with `limit_known` = 0 when no limit is recorded | Limits | ↑ |
| `limit_known` — 1 if the user recorded a limit for the provider, else 0 | Limits | none |

`income_to_due_gap_days` (instalment due days before the next income) was dropped in D-27: the label no longer depends on intra-month timing, so it would be a feature with no signal. It is shown to the user as a timing note instead. `balance_to_monthly_essentials` was dropped with the balance.

Features may be added or removed only through an ADR; changing one changes `feature_schema_hash`, which forces regenerating the dataset and retraining (§3, invariant 1).

**Model artefacts:** `backend/models/<engine>/<version>/` with the model file(s), `metadata.json` (training data version, feature list + hash, library versions, metrics, CV summary, calibration choice, git commit). The server refuses to start if the served artefact's feature hash differs from `features.py`.

---

## 4. Modules / Feature Areas

| Module | What it does |
|---|---|
| **Auth & users** | Username-only login, session token, user scoping, admin seeding script for tester accounts. |
| **Ledger** | Transactions CRUD, Income / Expense / Savings, a per-month income/expense/net summary (no account balance — D-27), categories with word-boundary matching. |
| **Import** | CSV upload → column mapping → preview with per-row edits and skip reasons → confirm. Persona CSVs and a generic bank-CSV mapping. |
| **Recurring items** | Detection suggestions from history, user confirmation, manual add/edit; the backbone of known flows. |
| **BNPL plans** | Provider-aware schedules (v1 port: sen maths, monthly fee rate, Atome checkout payment), mark paid (single and bulk), rename, delete-with-transactions, By month bills, provider limits, due-date reminders in-app. Providers (D-24): only **SPayLater, TikTok PayLater and Atome** are named and rule-driven (rules confirmed from real users' checkouts). Any other provider uses **"Other provider (manual)"**: the user types a provider name, first payment date, number of instalments and the instalment amount (or total payable) shown at checkout; the app splits the total exactly in sen and applies no fee formula or provider rule. |
| **Financial health forecasting** | Engine 1 as §3.1. |
| **BNPL risk classification** | Engine 2 as §3.1, risk check → confirm into a plan → frozen risk report. |
| **Dashboard** | Month summary (income, expenses, net), health gauge, 3-month margin band chart, BNPL stack (total monthly commitment across providers + due-date timeline), upcoming alerts, locked state below 4 months. |
| **Data generation** (`ml/datagen`) | Synthetic Malaysian-student population with documented, cited parameters; persona CSVs for UAT. |
| **Evaluation harnesses** (`ml/`) | Engine 1 comparison, Engine 2 training/selection, report-ready tables and figures in `reports/`. |
| **Model card / About** | In-app page: how the scores are made, data, limitations — for testers and examiners. |
| **UAT kit** | Tester seeding, persona CSVs, task script, SUS + explanation-clarity + pre/post decision vignettes, consent text, analysis script. |

---

## 5. Non-Goals

Explicitly out of scope. Revisit only by adding an ADR that says why.

- PDF bank-statement parsing (supervisor decision; cite conversion tools instead).
- Bank / open-banking / e-wallet API integration.
- Passwords, sign-up, OAuth, password reset (supervisor decision: username-only).
- New candidate algorithms outside the literature review — ETS, foundation models (Chronos, TimesFM, Moirai), EBM. Recorded as future work in the sources doc.
- Native mobile apps (the web app must work well on a phone browser).
- Push/SMS/email notifications (in-app reminders only).
- CCRIS/CTOS credit bureau integration.
- Investment tracking, peer comparison, social features.
- Using any tester's real financial data.

---

## 6. Build Roadmap

Phases are a dependency order only — no dates (author's instruction). Frontend screens for a module may be built as soon as that module's backend phase is green.

| Phase | Scope | Exit criteria |
|---|---|---|
| **P0 Foundation** | Monorepo skeleton (`backend/` uv project, `frontend/` Next.js), Ruff/pytest/Vitest/ESLint, Supabase project + migrations, username login + user-scoped repository layer, OpenAPI → TS client generation, dependency & memory spike for the full ML stack | Both apps boot; login works for two seeded users and each sees only their own rows (test); generated client compiles; spike report records which Python version installs every dependency and the backend's resident memory |
| **P1 Ledger & BNPL domain** | Port v1 domain modules + tests (schedule, providers, ledger, plans, bills, categorize), transactions/month-summary/plans/providers APIs, CSV import, recurring items (manual), provider limits with the financed/checkout split (D-28) | Ported v1 tests green; API round-trips for every endpoint; multi-user isolation tests pass |
| **P2 Synthetic population** | `ml/datagen`: cited parameter file, transaction-level generator, 3 persona CSVs (4 months each), Engine 2 profile set, Engine 1 cohort | Generator deterministic under a seed; distribution report vs cited targets; persona CSVs import cleanly through P1's importer |
| **P3 Engine 1 evaluation** | Datasets (MoneyData, Berka subsample, synthetic cohort, optional private log), candidates (Naive, Moving average, AutoARIMA, Prophet, global LSTM), rolling-origin harness, MASE/RMSSE/coverage/cumulative-margin-MAE, on both variable series (weekly discretionary spend and weekly unconfirmed income), HLN-DM + Wilcoxon + Friedman/Nemenyi | `reports/engine1/` tables + figures; winner chosen by the D-06 rule; decision recorded as an ADR |
| **P4 Engine 1 serving** | Recurring detection, variable series, served model, residual bootstrap, monthly-margin Monte Carlo, `/api/forecast`, health score, completeness warnings | Designed-case tests pass: a RM600 purchase over 3 months is Safe on RM2,000 monthly income, At Risk on RM500 monthly income, and At Risk on savings alone with no income; plus PTPTN lump-sum, bill collision, stacked instalments; forecast latency measured; 4-month gate enforced |
| **P5 Engine 2 training** | Simulation labels via served Engine 1, shared `features.py`, 4 candidates with monotone constraints, Optuna tuning, 5×5 CV, calibration, ablation, stress tests, artefacts + metadata | `reports/engine2/` tables + figures; winner + calibration ADR; ablation shows the Engine 1 contribution with a CI |
| **P6 Engine 2 serving** | `/api/risk/check` (with/without simulation, features, model, SHAP, counterfactuals, repayment flag), confirm → plan, frozen risk report | Designed cases from academic-constraints §5 pass; feature-hash guard tested; p vs p_simulated logged |
| **P7 Frontend** | All screens on the v1 design system: login, onboarding/import, dashboard, transactions, recurring, plans, risk checker, risk report, model card | Every screen has loading/empty/error/locked states; 375/768/1440 layouts; Playwright covers login → import → forecast → risk check → confirm |
| **P8 Deployment** | Vercel + Render + Supabase Singapore, env-driven URLs and CORS, keep-alive plan, functional-test checklist on the live URL | Fresh-session walkthrough on the live URL incl. a phone browser; memory within the host limit |
| **P9 UAT kit** | Tester seeding script, persona assignment, task script, SUS + explanation clarity + pre/post vignettes, short participant information note (synthetic data only), analysis script | Dry run with one tester; analysis script produces SUS mean + CI and the decision-switch table from the dry-run data |
| **P10 Optional** | LLM-phrased explanations from SHAP JSON with number check + template fallback; dissertation figure pack | Only after P0–P9 are green |

---

## 7. Decision Log

Canonical one-line list. Load-bearing entries are expanded as ADRs in `changelog/DECISIONS.md` under the same id.

| # | Decision | Why |
|---|---|---|
| D-01 | v2 is a new public repo; v1 is a frozen reference; proven v1 modules are ported with their tests | v1 was the experiment; its domain code is correct and tested, its engines are not reused |
| D-02 | Stack: Next.js (App Router, TS, Tailwind 4, Recharts) + FastAPI + Supabase Postgres; add uv, Ruff, TanStack Query, zod, Vitest, Playwright | Continuity with v1 and the concept document; additions fix v1's untested frontend and hand-mirrored types |
| D-03 | Username-only login issuing a signed bearer token; every query user-scoped in the repository layer; backend-only DB access, RLS on with no anon policies | Supervisor decision; bearer token avoids cross-site cookie issues between Vercel and Render |
| D-04 | Engine 1 = component forecaster: known flows placed, variable weekly series (spend, and income when unconfirmed) forecast, residual-bootstrap Monte Carlo, anchored to today (balance anchor removed by D-27) | v1's single net series lost to naive baselines, decayed to zero and had no uncertainty |
| D-05 | Candidates stay within the literature review (ARIMA/Prophet/LSTM; RF/XGB/LGBM; SHAP); only benchmarks (naive, moving average, logistic regression) and configurations (global LSTM, monotonic constraints, counterfactual search) are added | Methodology must follow from the reviewed literature; the real fixes are design, not algorithms |
| D-06 | Engine 1 selection: rolling-origin, pooled MASE primary; the served model is the best literature candidate unless it is significantly worse than the best benchmark, in which case the benchmark is served and that is reported as a finding | Honest selection; Objective 1 still names the best literature model |
| D-07 | Engine 2 target = simulated shortfall probability from Engine 1 (cumulative margin < RM0 at any month-end in the horizon, per D-27) | Defensible, cited, and makes the forecast → classifier link load-bearing |
| D-08 | One synthetic population generator feeds Engine 2 training, the Engine 1 cohort and the UAT persona CSVs; parameters cited in a single file | One set of assumptions to justify; supervisor's top methodology concern |
| D-09 | Engine 2 features defined once in `engines/risk/features.py`; artefacts carry a feature-schema hash checked at startup | v1's train/serve mismatches |
| D-10 | Engine 2 trained on soft labels (duplicate-and-weight); 5×5 repeated CV grouped by profile; Optuna tuning; Brier primary; corrected t-tests; nested-CV calibration | Rigour the supervisor asked for; reuses v1's proven harness |
| D-11 | Repayment history is a rule-based flag, not a model feature | Synthetic missed-payment behaviour distorted v1; BNM's 3-miss rule is citable as-is |
| D-12 | Explanations: SHAP top factors (≥ 0.02) with number-checked templates + exact grid counterfactuals over actionable levers | Literature-reviewed XAI + actionable recourse |
| D-13 | Input = CSV import + manual entry; PDF parsing out of scope | Supervisor decision |
| D-14 | No real personal data in the repo; private data only in gitignored `data/private/` | Public repo |
| D-15 | Hosting Vercel + Render + Supabase Singapore; the P0 spike showed torch pushes the process to ~607 MB, so the LSTM is served via ONNX Runtime and the backend never imports torch; if the served stack still exceeds ~450 MB, fall back to Google Cloud Run (1 GiB) | Supervisor plan, with a measured escape hatch |
| D-16 | All money arithmetic in integer sen | v1 lesson, pinned by tests |
| D-17 | Provider rules served by `GET /api/providers`; the frontend never mirrors them | Removes v1's hand-sync invariant |
| D-18 | TS API types generated from FastAPI's OpenAPI (`openapi-typescript` + `openapi-fetch`); drift fails the check | Removes v1's hand-mirrored `types.ts` |
| D-19 | ~~Running-ledger balance by default~~ — **superseded by D-27**: no balance is stored or needed | v1's manual-sync balance went stale; students rarely keep a reliable balance |
| D-20 | Risk bands pre-registered: Safe < 0.10, Caution 0.10–0.30, At Risk ≥ 0.30 on P(shortfall) | Bands must not be tuned on results |
| D-21 | Shortfall threshold is RM0 on the cumulative margin (the plan cannot be met from income); a RM50 buffer is a UI warning only | Objective, provider-meaningful definition |
| D-22 | TDD, 80% coverage target, conventional commits; Claude commits at verified phase ends, never pushes | Author's standing rules; pushes are done by the author |
| D-23 | Python version pinned via uv to one every ML dependency installs on (3.12, verified in P0) | Prophet, PyTorch, LightGBM, SHAP wheels on Windows and Render |
| D-24 | Only SPayLater, TikTok PayLater and Atome are named providers with schedule rules; every other provider uses a manual "Other provider" entry (user types dates and the checkout instalment amount) | Only these three have rules confirmed from real users; a guessed first due date creates phantom missed payments, and a flat monthly fee rate can't represent other providers' fees (v1 lesson) |
| D-25 | Berka is used only as a real-transaction benchmark for Engine 1 (and to pre-train the global LSTM), never as a model of the target population | Czech adult accounts from the 1990s; the student population is represented by the cited synthetic generator |
| D-26 | Money columns are bigint sen; user-owned tables link through composite (id, user_id) foreign keys | supabase-py returns numeric as float; the database itself should refuse cross-user links |
| D-27 | Engine 1 forecasts income and expense flows; there is no starting balance, no running ledger, no balance sync. Shortfall = cumulative margin < RM0 at a month-end | Students rarely keep a reliable balance and incomplete logs corrupted a balance anchor; BNM's own household stress test is margin-based |
| D-28 | A provider limit caps the financed amount; the excess is paid at checkout and counted in the purchase month | Author-confirmed real checkout behaviour; a purchase above the limit is otherwise impossible |
| D-29 | API money is integer sen (`*_sen`); refunds/transfers are reserved categories; CSV import is stateless with duplicate flagging | No float ever touches a ringgit amount; refunds must not inflate income; Render restarts lose in-memory state |
| D-30 | A payment is tied to its instalment (unique); ambiguous failures never delete a payment; create-plan logs payments before flipping checkout instalments | No transactions in supabase-py, and a timeout looks the same whether or not the database committed |
| D-31 | The synthetic population keeps answer keys under `truth`, builds the proposed purchase from the recorded limit only, draws repayment per student, and puts weekly-scale structure (not day-level) in the series | The first version leaked the true limit, applied a holder-level statistic per instalment and over-claimed difficulty; found by audit before any model saw it |
| D-33 | The cumulative margin starts at RM0 at the start of the current month and includes this month's actual net so far (amends D-27's "RM0 today") | Read literally, income received earlier this month was ignored while the rest of the month's bills were counted, so users looked At Risk on any day after payday |
| D-34 | Engine 1 serves the global LSTM (per kind), exported to ONNX; torch stays out of the API process | Best literature candidate by the D-06 rule: geometric-mean MASE 0.815 against 1.044 for the best benchmark, p = 2e-37, best on every dataset and history length; about 1 ms per forecast |
| D-35 | Forecast gate = 4 calendar months and 17 complete weeks; incomplete-month rules (no data / no income / low spend); actual before `forecast_from`, rules and model after; error paths with a 1.5x widening | Four calendar months can hold eight weeks of data; stale ledgers must not read as zero spending; short histories must widen the bands, not report false certainty |
| D-36 | A risk check simulates to the last instalment of the plan (bounded at 180 weeks); the dashboard forecast keeps its own 52-week default | The 52-week cap truncated 3,834 of the first 10,000 labels and made long plans look safer; found by audit before any training |
| D-37 | Engine 2 evaluation: a 10% lockbox scored once, both ablation arms tuned inside every fold, calibration fitted on single-repeat out-of-fold predictions and stored, subgroup results where the baseline is under 0.10, stress on the lockbox with an identity control | The first harness reported the winner on the folds that chose it and tuned the ablation on its own test folds |
| D-38 | Content-Security-Policy with a per-request script nonce (proxy), every page rendered per request, connect-src limited to this origin and the API, styles keep unsafe-inline | The session token is readable by injected script; blocking injected script and limiting where a running one can send is the main control; inline style attributes cannot carry a nonce |
| D-39 | Per-user limits on the forecast and import routes, 4-hour sessions in the blueprint, unguessable tester usernames enforced by the roster | One user must not starve the single worker; a stateless token cannot be revoked on logout; login takes only a username |
| D-40 | The risk model is served as ONNX with a calibrator stored as numbers; reasons are exact Shapley values against a stored reference student, threshold 0.02; start-up refuses a model whose feature hash, simulation constants or forecast-model checksums differ | The API image cannot carry shap and a tree library; contributions must be on the calibrated scale the student sees; v1's silent train/serve mismatch must not recur |
| D-41 | Smallest change = fixed grid (instalments, wait for income, price cut, other provider), one change before two, written effort order, first that reaches Safe, else an honest none | Explainable, cannot recommend what the model does not rate safe; the order is what makes 'smallest' defensible |
| D-42 | Import reads .xlsx/.xlsm (every sheet with a table; skipped sheets named) and takes a file's own Type and Category columns as written; header found in the first 30 rows; workbooks are size-checked before parsing | The importer trusted a guess over data the person typed; students keep budgets in Excel; a workbook is untrusted input on a small worker |
| D-43 | Twelve built-in categories plus BNPL are locked; the person's own are added, renamed and deleted (delete moves or merges), stored in `user_categories` (migration 0002); names travel in body or query, never the path | The engines key off Refund, Transfer and BNPL; her own file brought in categories the app could not manage |
| D-44 | Merchant text ignores month names ("Rent july" = "Rent august") | Each month looked like a different payee, so monthly items were never detected or matched |
| D-45 | Spending by category uses the month summary's definition of spent; transfers ignored, refunds netted off the total, savings shown beside spending (`ASSUMED:` not subtracted), BNPL its own row | One definition of "spent" on every screen |
| D-46 | The plan preview carries `fee_sen` and `total_cost_sen` from the server; the card says who pays what | The frontend computes no money; the old labels hid the fee and the real cost |
| D-47 | Competition variant: an assistant (Claude via the Anthropic API, key server-side) turns requests into calls on the existing engines; the LLM narrates and proposes, never produces a score, forecast or amount; number-checked narration; guided mode without a key | The theme asks for an agent that completes real tasks; the numbers stay in the measured engines (overrides D-05 for the assistant layer only) |
| D-48 | Three permission tiers (read, propose, write); the model has no write tool; writes run only from a user-confirmed, single-use, expiring pending action; full audit log | Permission tiers are scored; prompt injection can at most propose |
| D-49 | v3 login hardened: passphrase second factor, login rate limits, token revocation, write quotas, ledger cap, pagination, plan-create race fixed | Username-only login is the first security finding; the supervisor's rule bound the FYP only |
| D-50 | Optional savings buffer in Engine 1 (margin starts from it) and Engine 2 (new feature); labels regenerated, Engine 2 retrained, old and new numbers both reported | A student living on savings was wrongly At Risk (amends D-27) |
| D-51 | Apache-2.0 licence with NOTICE and THIRD_PARTY.md | Permissive with a patent grant; dependency licences checked compatible |
| D-52 | The artefact's forecast-settings digest ignores line endings | A Windows-trained artefact refused to load on Linux (and in the Docker image) |
| D-53 | The assistant's LLM is provider-agnostic (`LLM_PROVIDER`): Gemini free tier first, Claude via the Anthropic API as the upgrade | No credit yet; switching must be one setting (amends D-47's provider) |

---

## 8. Open Questions

Unresolved. Anything marked `ASSUMED:` is a working assumption, not a confirmed fact — it must be confirmed before anything load-bearing is built on it.

1. ~~Python 3.12 / Render memory~~ — resolved by the P0 spike (D-23, D-15; `reports/spikes/p0-dependency-spike.md`): 3.12 installs everything; torch must stay out of the served process.
2. *(was Q2 — resolved, see above)*
3. ~~Berka obtainable~~ — resolved in P3: the CTU Relational Repository's public guest database served all 4,500 accounts without a login (checksummed, `data/external/README.md`); Berka remains a benchmark only (D-25), and the global LSTM was not pre-trained on it.
4. ~~Horizon cap of 52 weeks for risk checks~~ — resolved in P5 (D-36): a risk check simulates to the last instalment of the plan, bounded at 180 weeks.
5. `ASSUMED:` Synthetic population size ~10,000 profiles is enough for stable 5×5 CV; P5 checks learning curves.
6. Providers other than SPayLater, TikTok PayLater and Atome are not named in the app until the author collects a real checkout example for each; until then they use the manual "Other provider" entry (D-24).
7. Whether the supervisor and faculty consultants want to review the simulation-derived label design before P5 training starts (recommended).

8. `ASSUMED:` (D-27) Shortfall is evaluated on the **cumulative** margin at each month-end starting from RM0 (savings not assumed), rather than on each month's margin alone. P5 reports the per-month definition as a sensitivity check.
9. `ASSUMED:` (D-28) The provider limit caps the financed **total payable including the monthly fee**, and a provider's used limit = the sum of its unpaid instalment amounts. Confirm against a real SPayLater / TikTok / Atome checkout before P1 closes; an unset limit means no cap (stated on the report).
10. `ASSUMED:` (D-27) Incomplete-month thresholds and the "unconfirmed income" series use the same candidate models and evaluation protocol as discretionary spend; both are fixed in P3/P4.
11. Known limitation, deliberate (D-27): a student living off savings with no income looks At Risk, because savings are not credited. An optional "savings buffer" input is recorded as future work.

UAT ethics/consent approval: not required (author, 2026-10-08) — testers use synthetic persona data only.

---

## 9. Glossary

| Term | Meaning |
|---|---|
| Engine 1 | Code name for financial health forecasting. Not used in user-facing text or the dissertation. |
| Engine 2 | Code name for BNPL risk classification. Same rule. |
| Known flows | Income, bills and instalments with known dates and amounts — placed, not forecast. |
| Discretionary spend | Expenses not tied to a recurring item or BNPL plan; the only forecast quantity. |
| Margin | Income less bills, BNPL instalments (including any checkout payment) and discretionary spending over a month. Cumulative margin starts at RM0 today — savings are not assumed (D-27). |
| Shortfall | The cumulative margin at a month-end is below RM0 in a simulated path: the plan could not be met from income alone. |
| P(shortfall) | Share of the 1,000 Monte Carlo paths with a shortfall within the horizon. |
| Financed amount / checkout payment | The part of a purchase the provider's remaining limit can cover, and the excess the user pays at checkout (D-28). |
| MASE | Mean Absolute Scaled Error — forecast error relative to the in-sample naive forecast; < 1 beats naive. |
| Brier score | Mean squared error between predicted probability and target; lower is better. |
| Soft label | A probability used as the training target instead of 0/1. |
| Persona | One of three UAT tester profiles: frequent BNPL, budget-conscious, irregular income. |
| Sen | 1/100 of a ringgit; all money maths is in integer sen. |
| DSR | Debt service ratio — monthly debt obligations / monthly income. |
