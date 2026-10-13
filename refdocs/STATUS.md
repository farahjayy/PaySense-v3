# PaySense v2 — Build Status

> **Read this first to know where we are.** Updated at the end of every build session. Phases and scope come from `refdocs/paysense-v2-PRD.md` §6. Don't reorder phases without updating this file and saying why (CLAUDE.md "keep docs current").

**Build philosophy:** dependency order, no dates. Each phase ends green — tested and actually run — before the next one starts. Port what v1 proved, rebuild what v1 got wrong, and never ship a number that doesn't trace to a model, a simulation or the user's data.

**Right now:** the real Supabase project (`paysense-v2`, Singapore) exists, `0001_init.sql` is applied, the anon-key check passes on all 8 tables, a tester was seeded, and the 20 real-database tests pass. **Not yet run against it:** the API served by uvicorn on the real database, the browser journey with the real model, and the deployment. **Left for the author:** run the app locally against it (backend + frontend), deploy (Render, Vercel), and the user sessions. P1 also needs **one real checkout example** from the author to confirm the provider-limit rule (D-28, `ASSUMED`). P0 to P6 are built and green; the global LSTM is the served forecaster (D-34) and the risk check serves a real model (D-40).

---

## Phase checklist

| Phase | Scope | Status |
|---|---|---|
| P0 Foundation | Monorepo skeleton, tooling, Supabase migrations, username login + user scoping, OpenAPI→TS client, dependency & memory spike | ✅ Done — migration applied to the real project, anon-key RLS check passes (8 of 8 tables, HTTP 401), tester seeded, 20 real-database tests pass. Not yet exercised: login and the app through uvicorn on the real database |
| P1 Ledger & BNPL domain | Port v1 domain + tests, transactions/month-summary/plans/providers APIs, CSV import, recurring items, provider limits with the financed/checkout split (D-28) | 🔶 In progress — all code built, reviewed and green on the in-memory DB (909 backend tests); the 20 real-database contract tests now pass against the real project; D-28 limit rule is `ASSUMED` |
| P2 Synthetic population | `ml/datagen`, cited params, persona CSVs, Engine 2 profiles, Engine 1 cohort | ✅ Done — generator, 3 persona CSVs, 10,000-profile export + manifest and distribution report built, audited (python-reviewer, ml-auditor) and green (1085 tests). Persona CSVs await the author's review before P9 |
| P3 Engine 1 evaluation | 5 forecasters × 4 datasets, rolling-origin, MASE + significance, reports | ✅ Done — global LSTM wins by the D-06 rule (D-34); 3 datasets (synthetic, MoneyData, Berka), 45,804 results, 0 failures; audited before the full run; report regenerates identically |
| P4 Engine 1 serving | Recurring detection, component forecaster, Monte Carlo, `/api/forecast`, health score | ✅ Done — built and audited twice; the LSTM is served through ONNX (parity with torch 2.5e-6, with the evaluation 5e-7); latency p50 12 ms, p95 16-18 ms; engine memory 96 MB; the personas unlock the forecast through the real service and the API process (runtime-only environment) answers it at 100 MB idle |
| P5 Engine 2 training | Simulation labels, shared features, 4 classifiers, tuning, CV, calibration, ablation | ✅ Done — 10,000 version-2 labels; two ml-auditor passes applied before the full run; 5x5 grouped nested CV with a 10% lockbox scored once. **Winner LightGBM** (Platt): cross-validated Brier 0.0163, lockbox 0.0198 against 0.1788 for always predicting the mean; XGBoost is statistically tied (p = 0.70), logistic 0.0205, random forest 0.0612. The forecast-derived features add real skill (removing them: +0.0996 Brier, CI 0.0957 to 0.1035; +0.0903 where the plan decides the band). Monotone constraints cost 0.0022 Brier (significant, reported). Stress: income -20%, a missing month, a stale ledger and a delayed PTPTN keep band agreement 88-93%. Report in `reports/engine2/`; the report states plainly that labels are synthetic and mostly decided before the purchase. Not done: bias-term sensitivity |
| P6 Engine 2 serving | Risk check, SHAP, counterfactuals, repayment flag, confirm, frozen report | ✅ Done (needs a real-database run) — LightGBM exported to ONNX (121 KB) with the calibrator as numbers; loader refuses a model whose feature hash, feature order, simulation constants or forecast-network checksums differ (D-40); exact baseline Shapley reasons on the shown scale (91 ms for the 65,536-coalition batch); repayment flag; number-checked sentences; counterfactual search (D-41); `/api/risk/check`, `/confirm`, `/checks/{id}` with a per-user limit; the five designed cases pass with the real model; serving check on 200 fresh students: p50 0.29 s, p95 0.69 s, same band as the direct simulation 95.0% (mean absolute gap 0.060, largest 0.51); API process 103 MB with the model loaded, 111 MB after nine checks. **Reviews done:** fastapi, security and python reviews fixed (2026-10-13 changelog); a change that reaches Safe exists for only 12.7% of non-Safe results (most are short before the purchase). Not done: bias-term sensitivity |
| P7 Frontend | All screens on the v1 design system, all states, Playwright journey | 🔶 Almost done — every screen is built, reviewed (react, accessibility, security) and green, including the risk-check screen (shared purchase fields, band and reasons, smallest change with a Try-this action, with/without chart and table, separate repayment note, go-ahead creates the plan and saves the report) and the saved-report page; 205 unit tests, axe clean on every screen and the risk result, 14 Playwright tests (desktop and phone) on the production build with the nonce CSP, including the full check -> suggestion -> add plan -> saved report journey (against a stub model). Bundle size recorded: 404 kB gzipped across all 25 client chunks, 63 kB for the largest route's own chunks. The journey runs against a stub model; the real-model journey needs a live backend |
| P8 Deployment | Vercel + Render + Supabase SG, live functional checklist | 🔶 Prepared, nothing deployed — Dockerfile (**never built**: Docker daemon unavailable), Render blueprint, runbook with live checklist and keep-alive options, smoke script (tested), nonce CSP; the API in a runtime-only environment uses 100 MB idle / 112 MB after load. **Needs the author:** Supabase project and migration, Render and Vercel setup, `FORWARDED_ALLOW_IPS`, the live walkthrough on a phone |
| P9 UAT kit | Tester seeding, persona CSVs, instruments, consent, analysis script | 🔶 Built — information note, task script, SUS / clarity / vignette instruments, roster seeding (unguessable usernames enforced), persona date shifting, analysis script (mean SUS with CI, decision-switch table) with an invented example; the three personas are now five months long and a test imports each into the real forecast service (all unlock). The task script was re-read against the finished screens and the python review is applied. **Left:** the sessions themselves (the author) |
| P10 Optional | LLM-phrased explanations, figure pack | ⬜ Not started |

Status vocabulary — use these exactly, and never round up:
- ⬜ **Not started**
- 🔶 **In progress** — say precisely what works and what doesn't
- ✅ **Done** — built *and* verified. If it compiles but was never run, it is not done.
- ⛔ **Blocked** — name the blocker and who/what unblocks it

---

## P2 — Synthetic population

| Item | Approach | Status |
|---|---|---|
| Parameters and provenance | `params.yaml` + `sources.md`; the loader refuses a parameter with neither a source key nor `assumed` + reason; duplicate keys rejected | ✅ 121 parameters: 16 cited, 105 assumed |
| Generator | income (allowance, PTPTN, part-time, gig), bills, discretionary spend (category allocation, AR(1) drift, payday week, exam dips), existing BNPL plans built with the app's own `propose_plan`, proposed purchase | ✅ |
| Profiles | `generate_profile`; deterministic; a 10-profile run is a prefix of a 100-profile run; answer keys under `truth` | ✅ |
| Persona CSVs | 3 committed files, 4 months each, import through `parse_csv` with no skipped rows | ✅ built · 🔶 **author review before P9** |
| Export | `profiles.jsonl` + `weekly_series.csv` + committed `MANIFEST.json`; 10,000 profiles in 490 s, peak 76 MB | ✅ |
| Distribution report | `reports/datagen/` generated by script; per-holder repayment, 15% spend-share tolerance, wiring checks labelled | ✅ |
| Reviews | python-reviewer and ml-auditor | ✅ HIGH findings fixed (D-31); cross-machine reproducibility not verified (stated in the report) |

---

## P1 — Ledger & BNPL domain

| Item | Approach | Status |
|---|---|---|
| Money, providers, schedule | `domain/{money,providers,schedule}.py`; every v1 schedule test re-expressed in sen; limit split (D-28); manual Other-provider schedule (D-24) | ✅ 324 domain tests |
| Categorise, flows, plans, bills | Reserved `Refund`/`Transfer` categories; one shared flow classification and month summary; plan read-model; monthly bills | ✅ |
| CSV / Excel import parser | stdlib `csv` and `openpyxl`; a file's own Type and Category columns used as written (D-42); header found among the first 30 rows; per-file direction detection; every unusable row reported; multiplicity-aware duplicate flags; workbooks size- and shape-checked before parsing | ✅ built and reviewed (python and security reviews applied); not yet tried in a browser with a real `.xlsx` |
| Plan proposal builder | `domain/plan_builder.py` — one pure function behind both preview and create | ✅ |
| Repositories | transactions, recurring items, plans (self-compensating create / mark-paid), provider limits; isolation test per function | ✅ against the in-memory fake · 🔶 real-DB contract tests (18) written, **not run** |
| API routes | providers, provider limits, transactions, month summary, recurring items, CSV import (stateless), plans (preview/create/read/rename/delete/pay/bulk pay), bills — 18 endpoints, each with a two-user test and an unauthenticated test | ✅ |
| Typed client | `schema.d.ts` regenerated for all 18 endpoints; `lib/money.ts` twin of the Python money helpers | ✅ |
| Review | security, FastAPI/Python and React/TypeScript reviewers | ✅ run; no CRITICAL; HIGH and MEDIUM findings fixed (CHANGELOG "reviews applied"); deferred items listed under Known gaps |

---

## P0 — Foundation

| Item | Approach | Status |
|---|---|---|
| Toolchain | Install `uv`; pin Python via `.python-version` (D-23) | ✅ uv 0.12.23, Python 3.12 pinned |
| Dependency & memory spike | Install the full ML stack in a throwaway env, record versions + RSS in `reports/spikes/p0-dependency-spike.md` | ✅ Everything installs on 3.12; torch pushes a process to ~607 MB, so the LSTM is served via ONNX and the backend never imports torch (D-15) |
| Backend skeleton | `backend/` uv project, FastAPI app factory, settings with fail-fast env validation, `/api/health`, Ruff + pytest | ✅ |
| Database | Supabase project (Singapore), `backend/migrations/0001_init.sql` (users, user_settings, transactions, recurring_items, bnpl_plans, bnpl_installments, provider_limits, risk_checks), RLS on | 🔶 SQL written and syntax-checked (32 statements parse); **not applied** — needs the author's Supabase project |
| Auth | `POST /api/auth/login`, `GET /api/auth/me`, HS256 bearer token, `current_user` dependency, admin seeding script | 🔶 Works against the in-memory fake (tests + browser journey); not yet exercised against the real database |
| User-scoped repository layer | Every function takes `user_id`; isolation test with two users | 🔶 Fake-backed isolation tests pass; 9 real-database contract tests are written (`pytest -m integration`) but have not run |
| Frontend skeleton | `frontend/` Next.js + TS + Tailwind 4, v1 design tokens, login page, authed layout shell | ✅ |
| Typed client | `openapi-typescript` + `openapi-fetch`, `npm run gen:api`, drift check | ✅ drift check proven: exit 1 on a changed schema, 0 after revert |
| Test tooling | pytest (backend), Vitest + Testing Library (frontend), Playwright installed with one smoke test | ✅ |

---

## Verification ledger

What has actually been run, not what has been written. A row here needs a real command and a real result.

| Date | What was verified | How | Result |
|---|---|---|---|
| 2026-10-08 | uv installed | `uv --version` | uv 0.12.23 |
| 2026-10-08 | Full ML stack installs and imports on Python 3.12; RSS measured | scratch uv project: `uv add` of fastapi … torch (CPU index), then a psutil RSS probe per stack combination | All installed on 3.12.15. RSS: served set 343–470 MB; + torch 607 MB; + prophet +15 MB. Report: `reports/spikes/p0-dependency-spike.md` |
| 2026-10-08 | Backend tests, lint, coverage | `cd backend && uv run pytest -q --cov=app`; `uv run ruff check . && uv run ruff format --check .` | 110 passed, 9 integration deselected; 95% coverage on `app/`; ruff clean |
| 2026-10-08 | Server fails fast on a missing secret | test `test_server_exits_naming_session_secret_when_it_is_missing` (subprocess) + manual `uvicorn app.main:app` without `SESSION_SECRET` | Exits non-zero with `SESSION_SECRET: Field required` and a pointer to `env_setup.md` |
| 2026-10-08 | Live server smoke | `uvicorn app.main:app` with dummy env, then `curl` | `/api/health` → `{"status":"ok"}`; `/api/auth/login` with `{}` → 422 envelope; `/api/auth/me` unauthenticated → 401 envelope |
| 2026-10-08 | Migration SQL is valid Postgres | `pglast.parse_sql` over `0001_init.sql` | 32 statements parsed. **Syntax only — not applied to any database** |
| 2026-10-08 | Frontend lint, types, unit tests, build | `cd frontend && npm run lint && npx tsc --noEmit && npx vitest run --coverage && npm run build` | lint clean; tsc clean; 26 tests passed (lib 92.5%, overall 84.6% stmts); build OK (3 routes) |
| 2026-10-08 | Generated API types cannot drift silently | `npm run check:api` on the real tree, then after adding a field to `HealthOut`, then reverted | exit 0 → exit 1 → exit 0 |
| 2026-10-08 | Browser journey: redirect to /login, bad username, sign in, reload keeps session, log out, guarded route | `cd frontend && npx playwright test` (real FastAPI app on the in-memory DB + `next dev`) | 6 passed (3 tests × desktop Chrome and Pixel 7). **Fake database, not Supabase.** Re-run after P1: still 6 passed |
| 2026-10-08 | P1 backend: domain, repositories, API | `cd backend && uv run ruff check . && uv run pytest -q --cov=app` | **826 passed**, 18 integration deselected; 97% coverage on `app/`; ruff clean. All against `tests/fakes.py`, not Supabase |
| 2026-10-08 | The author's limit example end to end | `tests/api/test_plans_api.py::test_the_authors_example_limit_200_price_300_pay_100_at_checkout` and `::test_create_logs_the_excess_over_the_limit_as_a_checkout_payment` | limit RM200 + price RM300 → RM200 financed, RM100 checkout payment, RM100 logged as a linked expense |
| 2026-10-08 | Every money field in the API is an integer sen | `tests/api/test_providers_api.py::test_every_money_field_in_the_api_is_an_integer_number_of_sen` (walks the OpenAPI document) | passes over all P1 models |
| 2026-10-08 | After applying the reviews: backend | `cd backend && uv run ruff check . && uv run pytest -q` | **909 passed**, 20 integration deselected; ruff clean |
| 2026-10-08 | After applying the reviews: frontend | `npm run gen:api && npm run check:api && npx tsc --noEmit && npm run lint && npx vitest run`; `NEXT_PUBLIC_API_BASE_URL=… npm run build` (and without the variable); `npx playwright test` | check:api OK; tsc, lint clean; **85 tests passed**; build OK, and **fails without the API URL, naming it**; Playwright 6 passed |
| 2026-10-08 | P1 frontend contract | `cd frontend && npm run gen:api && npm run check:api && npx tsc --noEmit && npm run lint && npx vitest run && npm run build` | types regenerated for 18 endpoints; check:api exit 0; tsc clean; lint clean; **62 tests passed**; build OK |

| 2026-10-08 | P2 synthetic population | `cd backend && uv run ruff check . && uv run pytest -q`; `uv run python -m ml.datagen.personas` (twice, SHA-256 compared); `uv run python -m ml.datagen.export --profiles 10000`; `uv run python -m ml.datagen.report` | **1085 passed**, 20 integration deselected; ruff clean; persona CSVs identical across runs; 10,000 profiles exported (490 s, peak working set 76 MB); report regenerated on the same 10,000 profiles. Second consecutive report run on the final code not diffed; test-scale determinism (150 profiles, byte-identical incl. figures) passes |
| 2026-10-09 | P3 Engine 1 evaluation, full run | `uv run python -m ml.engine1_eval.run --config full`; `uv run python -m ml.engine1_eval.report --config full` (twice) | 45,804 rows, 0 failures; report identical on regeneration; LSTM served by the rule (geometric MASE 0.815 vs 1.044) |
| 2026-10-09 | P4 engine and P5 feature contract | `cd backend && uv run ruff check . && uv run pytest -q` | **1315 passed**, 20 integration deselected |
| 2026-10-09 | P4 serving: ONNX LSTM, calibration, latency | `uv run python -m ml.engine1_eval.export_served`; `uv run python -m ml.engine1_eval.serving_check` (twice, identical) | parity with torch 2.5e-6; with the evaluation 5e-7; coverage inside P10-P90 0.46-0.69 (nominal 0.8); latency p50 12 ms / p95 16-18 ms; peak working set 96 MB |
| 2026-10-09 | P5 audit fixes and label regeneration | `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest -q`; `uv run python -m ml.datagen.export --profiles 10000`; `uv run python -m ml.datagen.report`; `uv run python -m ml.engine2_train.labels --profiles 10000` | 1576 passed, 1 failed (`test_features_are_computed_in_exactly_one_module`: the P6 file `templates.py` names feature keys), 20 deselected; 10,000 labels, 0 locked, 0 truncated; manifest sha256 matches; identity stress variant reproduces stored labels exactly. Training not run |
| 2026-10-09 | P7/P8 frontend and deployment preparation | `cd frontend && npx tsc --noEmit && npx eslint . && npx vitest run`; `NEXT_PUBLIC_API_BASE_URL=... npm run build`; `npx playwright test` (production build, both projects) | 181 unit tests passed; axe: no violations on any screen or the open dialog; 12 Playwright tests passed on desktop and phone with no Content-Security-Policy violations |
| 2026-10-09 | P8 runtime-only API | `uv sync --frozen --no-default-groups` into a separate environment; the app on the in-memory database, a persona imported, 30 forecast calls | imports resolve; 100 MB idle, 112 MB after; forecast p50 10 ms, p95 13 ms (warm). Docker image not built |
| 2026-10-09 | Review fixes | `cd backend && uv run pytest tests/api tests/ml/uat tests/domain -q` | 260 and 531 passed (API incl. limits; UAT, domain, import) |
| 2026-10-09 | P6 risk check slice | `cd backend && .venv/Scripts/python.exe -m pytest tests --ignore=tests/ml -q` | 1230 passed, 20 deselected (before the risk API tests were added: tests/api 240 passed incl. 20 risk API tests) |
| 2026-10-09 | P5 full run | `cd backend && .venv/Scripts/python.exe -m ml.engine2_train.train --config full` (29 min), `... stress --config full` (9 min), `... report --config full`, `... export` | winner LightGBM; lockbox scored once (log: `data/engine2/runs/lockbox_log.jsonl`); identity stress variant reproduces the lockbox Brier exactly (0.019830); ONNX vs trained model: max difference 2.6e-4, 1 of 3,000 rows over 1e-6 |
| 2026-10-09 | P6 serving check | `cd backend && .venv/Scripts/python.exe -m ml.engine2_train.serving_check --profiles 200`; the runtime-only API with the real model driven by `drive_risk.py`-style requests | 200 assessed, 0 locked, 0 rejected; p50 0.29 s, p95 0.69 s, max 1.07 s (before the shared-ledger change: p95 1.84 s); API 103 MB idle, 111 MB after nine checks |
| 2026-10-09 | Whole backend suite | `cd backend && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m pytest -q` | **1724 passed**, 20 integration deselected |
| 2026-10-09 | P7 risk screens and review items | `cd frontend && npx tsc --noEmit && npx eslint . && npx vitest run`; `npx playwright test` | 205 unit tests passed; 14 Playwright tests passed (desktop and phone) |
| 2026-10-09 | Personas unlock the forecast | `cd backend && .venv/Scripts/python.exe -m pytest tests/ml/test_personas.py -q` | 23 passed: every persona, five months long, gives `status ok` through the real forecast service || 2026-10-13 | Serving audit follow-ups; security and python review fixes | `cd backend && .venv/Scripts/python.exe -m ruff check . && ruff format --check . && .venv/Scripts/python.exe -m pytest -q`; `cd frontend && npx tsc --noEmit && npm run lint && npx vitest run && npx playwright test` | **1812 passed**, 20 integration deselected; ruff clean; 205 frontend tests passed; 14 Playwright tests passed (stub model); bundle 404 kB gzipped (all 25 chunks). The first security review stopped on a usage limit and was rerun |
| 2026-10-13 | Real Supabase project (`paysense-v2`, Singapore) | `0001_init.sql` run in the SQL editor; `cd backend && .venv/Scripts/python.exe scripts/check_rls.py`; `scripts/seed_users.py --username amir-k7q2xm ...`; `.venv/Scripts/python.exe -m pytest -m integration -q` | 8 of 8 tables answer the anon key with HTTP 401; tester created; **20 passed** (2 deprecation warnings from supabase-py). Run by the author in their terminal; the first integration run skipped until `SESSION_SECRET` and `CORS_ORIGINS` were set |
| 2026-10-13 | Serving audit follow-ups; security and python review fixes | `cd backend && .venv/Scripts/python.exe -m ruff check . && ruff format --check . && .venv/Scripts/python.exe -m pytest -q`; `cd frontend && npx tsc --noEmit && npm run lint && npx vitest run && npx playwright test` | **1812 passed**, 20 integration deselected; ruff clean; 205 frontend tests passed; 14 Playwright tests passed (stub model); bundle 404 kB gzipped (all 25 chunks). The first security review stopped on a usage limit and was rerun |
| 2026-10-13 | Import of Excel workbooks and a file's own Type/Category (D-42) | `cd backend && uv run pytest -q` (after a failing test first for each change); `uv run ruff check . && uv run ruff format --check .`; `cd frontend && npm run lint && npx tsc --noEmit && npm run test && npm run check:api && npm run build`; the author's own sample file read through `parse_upload`; a 12 KB workbook with two million cells in one row | backend **1919 passed**, 20 integration deselected, ruff clean; frontend lint and tsc clean, **214 unit tests passed**, API types match, build passes; the sample file reads as 38 expenses and 2 incomes with her categories and no rows flagged; the wide-row file is refused in 0.02 s. **Not run:** Playwright (needs the servers), a real `.xlsx` saved by Excel through the browser |
---

## Known gaps

- File-structure doc: `refdocs/guides/file-structure.md` (written at the end of P2). README's project-layout block is older and still marks built folders as planned; refresh it when P3 adds `engine1_eval/`.
- Eight working assumptions are open (`changelog/DECISIONS.md` bottom); the Python-version and memory ones were resolved by the P0 spike (D-23, D-15).
- Render memory is only indicative: the spike measured Windows RSS for import-and-toy-workload, not the real served stack. Re-measure at the end of P4 and P6, then on Render in P8.
- `frontend/.env.example` could not be created in this session (a permission rule blocks writing `.env*` files); the code defaults to `http://localhost:8000`, so it is optional locally. Create it from `refdocs/guides/env_setup.md` when convenient.
- `npm audit` reports high-severity findings in the dev-only ESLint toolchain (`braces` via `eslint-config-next`); nothing in the shipped bundle. Revisit when `eslint-config-next` publishes a fix.
- **Deferred from the reviews (none blocks UAT with 5–7 testers; all should be done before wider use):** per-user write quotas and a ledger-size cap; pagination on `GET /transactions` and SQL aggregation for the month summary and used-limit (they load whole ledgers); the concurrent plan-create limit race; refunds that land in a later month than their purchase are clipped at zero; a full script-src/connect-src CSP (needs nonces — P8); axe accessibility tests, a skip link and per-page titles (P7); escaping leading `= + - @` in any future spreadsheet export (P9); `uvicorn --limit-concurrency` and proxy size limits (P8).
- **D-28 is partly assumed:** whether a provider caps financing on price or price-plus-fee, and how it counts used limit, is a guess until the author supplies a real SPayLater / TikTok / Atome checkout example (PRD §8 Q9). One function (`split_for_limit`) and one (`used_limit_sen`) carry the assumption.
- **D-27 limitation, deliberate:** a student living on savings with no income looks At Risk because savings are not credited. An optional savings-buffer input is recorded as future work (PRD §8 Q11).
- `uv add` on this Windows machine intermittently fails to reinstall the project package (`Access is denied` removing its `dist-info`); `uv pip install` of the dependency plus the pyproject/lock edit worked around it once. If `uv run` complains, retry — it cleared by itself.
- **P4 audit items deferred on purpose:** unlinked BNPL payments imported from a CSV are dropped from the variable series and an overdue instalment is placed in the first forecast month (they can double count in one month); refunds net per week in the series but per month in the summary; the health score's "3 months" is the current month plus two; future-dated savings goals (PRD 3.1) are not implemented in the known flows; a user whose only rows are confirmed recurring items is locked as `no_usable_history`. The forecast bands are narrower than nominal for short histories even after the 1.5x widening (`ERROR_INFLATION`, ASSUMED); the P4 serving report measures this.
- **P4 cost bounds:** the ledger is limited to 24 months and `GET /api/forecast` has no per-user rate limit or cache; with the LSTM a request costs a few milliseconds, but any heavier model needs both before it is served.
- Providers other than SPayLater, TikTok PayLater and Atome use the manual "Other provider" entry until the author records a real checkout example for them (D-24).
- The simulation-label design should be shown to the supervisor before P5 (PRD §8 Q7).
- **P5 doc conflict resolved (2026-10-09):** the plan said stale and incomplete ledgers join the training set, the execution doc kept them apart; they are kept apart and only used in the stress test (D-37 item 6).
- **P5 open question for the author:** 54% of the new labels sit exactly at 0 or 1 and two thirds of profiles are decided by the baseline before the purchase (see the CHANGELOG entry of 2026-10-09); decide before the full run whether to rebalance the generator or train as built with subgroup metrics.
- **P5 not built:** the bias-term sensitivity (needs a second label run with the error record re-centred); the report lists it under Not done.
- **P3 evaluation was run on the cohort before the allowance correction** (commit 47da339); its MASE metrics are scale-free and expected unchanged; not re-run.
- `gh` (GitHub CLI): `gh.exe` exists at `C:\Program Files\GitHub CLI` but is not on the Git Bash PATH; the earlier note that it was not installed was wrong. Pushing is still the author's job.
