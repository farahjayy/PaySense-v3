# PaySense v2 — Build Status

> **Read this first to know where we are.** Updated at the end of every build session. Phases and scope come from `refdocs/paysense-v2-PRD.md` §6. Don't reorder phases without updating this file and saying why (CLAUDE.md "keep docs current").

**Build philosophy:** dependency order, no dates. Each phase ends green — tested and actually run — before the next one starts. Port what v1 proved, rebuild what v1 got wrong, and never ship a number that doesn't trace to a model, a simulation or the user's data.

**Right now:** P0 is built and green everywhere that does not need the live database. **Blocked on the author:** create the Supabase project (Singapore), put `SUPABASE_URL` and the secret key into `backend/.env`, apply `backend/migrations/0001_init.sql` in the SQL editor, and optionally set `SUPABASE_ANON_KEY` for the RLS check. Then run (from `backend/`) `uv run python scripts/check_rls.py`, `uv run python scripts/seed_users.py ...` and `uv run pytest -m integration` — those three are the only P0 items still unverified. P1's pure-domain ports (schedule, providers, ledger maths) do not need the database and proceed meanwhile.

---

## Phase checklist

| Phase | Scope | Status |
|---|---|---|
| P0 Foundation | Monorepo skeleton, tooling, Supabase migrations, username login + user scoping, OpenAPI→TS client, dependency & memory spike | 🔶 In progress — everything verified except the live-Supabase steps (migration applied, anon-key RLS check, integration tests, real-DB login) |
| P1 Ledger & BNPL domain | Port v1 domain + tests, transactions/month-summary/plans/providers APIs, CSV import, recurring items, provider limits with the financed/checkout split (D-28) | ⬜ Not started — plan + execution docs next (balance logic dropped by D-27) |
| P2 Synthetic population | `ml/datagen`, cited params, persona CSVs, Engine 2 profiles, Engine 1 cohort | ⬜ Not started |
| P3 Engine 1 evaluation | 5 forecasters × 4 datasets, rolling-origin, MASE + significance, reports | ⬜ Not started |
| P4 Engine 1 serving | Recurring detection, component forecaster, Monte Carlo, `/api/forecast`, health score | ⬜ Not started |
| P5 Engine 2 training | Simulation labels, shared features, 4 classifiers, tuning, CV, calibration, ablation | ⬜ Not started |
| P6 Engine 2 serving | Risk check, SHAP, counterfactuals, repayment flag, confirm, frozen report | ⬜ Not started |
| P7 Frontend | All screens on the v1 design system, all states, Playwright journey | ⬜ Not started |
| P8 Deployment | Vercel + Render + Supabase SG, live functional checklist | ⬜ Not started |
| P9 UAT kit | Tester seeding, persona CSVs, instruments, consent, analysis script | ⬜ Not started |
| P10 Optional | LLM-phrased explanations, figure pack | ⬜ Not started |

Status vocabulary — use these exactly, and never round up:
- ⬜ **Not started**
- 🔶 **In progress** — say precisely what works and what doesn't
- ✅ **Done** — built *and* verified. If it compiles but was never run, it is not done.
- ⛔ **Blocked** — name the blocker and who/what unblocks it

---

## P0 — Foundation (current phase)

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
| 2026-10-08 | Browser journey: redirect to /login, bad username, sign in, reload keeps session, log out, guarded route | `cd frontend && npx playwright test` (real FastAPI app on the in-memory DB + `next dev`) | 6 passed (3 tests × desktop Chrome and Pixel 7). **Fake database, not Supabase** |

---

## Known gaps

- A file-structure doc is still worth writing once P1 adds the domain layer; README §Project layout carries the tree meanwhile.
- Three working assumptions are open (`changelog/DECISIONS.md` bottom); the Python-version and memory ones were resolved by the P0 spike (D-23, D-15).
- Render memory is only indicative: the spike measured Windows RSS for import-and-toy-workload, not the real served stack. Re-measure at the end of P4 and P6, then on Render in P8.
- `frontend/.env.example` could not be created in this session (a permission rule blocks writing `.env*` files); the code defaults to `http://localhost:8000`, so it is optional locally. Create it from `refdocs/guides/env_setup.md` when convenient.
- `npm audit` reports high-severity findings in the dev-only ESLint toolchain (`braces` via `eslint-config-next`); nothing in the shipped bundle. Revisit when `eslint-config-next` publishes a fix.
- Providers other than SPayLater, TikTok PayLater and Atome use the manual "Other provider" entry until the author records a real checkout example for them (D-24).
- The simulation-label design should be shown to the supervisor before P5 (PRD §8 Q7).
- `gh` (GitHub CLI): `gh.exe` exists at `C:\Program Files\GitHub CLI` but is not on the Git Bash PATH; the earlier note that it was not installed was wrong. Pushing is still the author's job.
