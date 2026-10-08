# Execution — P0 Foundation

> Plan: `refdocs/plans/2026-10-08-p0-foundation.md`. Tasks run top to bottom. Each task carries its own **Verify** step, and a task is not done until its Verify actually passes — not when the code compiles.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4). A stale execution doc is worse than none.

## Before starting

- Read `CLAUDE.md`, `.claude/memory/preflight.md`, `refdocs/STATUS.md`, PRD §3, and ADRs D-02, D-03, D-15, D-18, D-23.
- Tools present: Git, Node 24, Python 3.14 (system). `uv` is **not** installed yet (Task 1).
- The author must create a Supabase project (region: Southeast Asia (Singapore)) and supply `SUPABASE_URL` + the secret/service key into `backend/.env` herself. Ask once, then keep building everything that doesn't need the live DB.
- v1 reference (read-only): `../PaySense/frontend/app/globals.css`, `../PaySense/frontend/postcss.config.mjs`, `../PaySense/frontend/components/layout/Nav.tsx`, `../PaySense/frontend/components/ui/`, `../PaySense/docs/UI_SPEC.md`, `../PaySense/backend/app/errors.py`.

---

### Task 1 — Install uv
- **Files:** none.
- **Steps:** install uv via the official Windows installer (`powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`), open a new shell.
- **Verify:** `uv --version` prints a version.

### Task 2 — Dependency & memory spike
- **Files:** `reports/spikes/p0-dependency-spike.md` (new), a throwaway env outside the repo (scratch dir).
- **Steps:**
  1. `uv python install 3.12`, create a scratch project, `uv add fastapi uvicorn pydantic supabase pyjwt pandas numpy statsforecast prophet torch onnxruntime scikit-learn xgboost lightgbm shap optuna scipy statsmodels` (torch from the CPU index: read PyTorch's current install instructions first).
  2. If anything fails to resolve or install, retry on 3.11. Record which package failed and why.
  3. Write a tiny script that imports the **served** set (fastapi, pandas, numpy, statsforecast, scikit-learn, xgboost, lightgbm, shap, onnxruntime — and separately torch, prophet) and prints resident memory (`psutil` or `resource`) after import and after one dummy forecast/prediction.
  4. Record the versions, Python version and RSS figures in the spike report.
- **Verify:** the report lists every package with a version and two RSS numbers (served set without torch/prophet; with them). Update D-23 and D-15 in `DECISIONS.md` (remove their `ASSUMED:` lines) and PRD §8 Q1–Q2.

### Task 3 — Backend skeleton
- **Files:** `backend/pyproject.toml`, `backend/.python-version`, `backend/app/main.py`, `backend/app/core/settings.py`, `backend/app/core/errors.py`, `backend/app/api/health.py`, `backend/tests/conftest.py`, `backend/tests/test_health.py`, `backend/.env.example`.
- **Steps:** `uv init` with the pinned Python; add runtime deps for P0 only (fastapi, uvicorn[standard], pydantic-settings, supabase, pyjwt, python-dotenv) and dev deps (pytest, httpx, ruff). App factory `create_app()`. Settings validate required env vars and raise a message naming the missing variable and `refdocs/guides/env_setup.md`. Error envelope `{"detail": {"code", "message"}}` (port v1's `errors.py` pattern). Ruff config in `pyproject.toml`.
- **Verify:** `cd backend && uv run pytest` → health test passes; `uv run ruff check .` clean; starting the app without `SESSION_SECRET` exits with a message naming it.

### Task 4 — Migration 0001
- **Files:** `backend/migrations/0001_init.sql`, `backend/migrations/README.md` (how to apply: Supabase SQL editor, in order).
- **Steps:** create every PRD §3.2 table (`users`, `user_settings`, `transactions`, `recurring_items`, `bnpl_plans`, `bnpl_installments`, `provider_limits`, `risk_checks`) with `user_id uuid not null references users(id) on delete cascade` (except `users`), v1's check constraints (amount > 0, types, instalments 1–36), indexes on `(user_id, date)` etc., `alter table … enable row level security` on all, no policies. Case-insensitive unique username (`unique (lower(username))`). Read v1's `backend/db/schema.sql` + migrations 001–004 first and carry every constraint forward.
- **Verify:** the author runs it in the Supabase SQL editor; then a query with the **anon** key returns zero rows / permission denied for every table (record the command in the ledger).

### Task 5 — DB client + user-scoped repository base
- **Files:** `backend/app/db/client.py`, `backend/app/db/users.py`, `backend/app/db/base.py`, `backend/tests/fakes.py` (in-memory fake repo, as v1 did in `tests/conftest.py`).
- **Steps:** read the installed supabase-py's client API first. Repository functions take `user_id` first; `users.get_by_username` is the only unscoped read. Tests run against the in-memory fake by default; a marked integration test hits the real DB when `SUPABASE_URL` is set.
- **Verify:** `uv run pytest` passes with the fake; `uv run pytest -m integration` passes once credentials exist.

### Task 6 — Username login
- **Files:** `backend/app/api/auth.py`, `backend/app/core/security.py`, `backend/app/api/deps.py` (`current_user`), `backend/scripts/seed_users.py`, `backend/tests/test_auth.py`, `backend/tests/test_user_isolation.py`.
- **Steps:** `POST /api/auth/login {username}` → case-insensitive lookup → HS256 token (`sub`=user id, `exp`=now+`SESSION_TTL_HOURS`). `GET /api/auth/me`. `current_user` rejects missing/forged/expired tokens with 401 + envelope. `seed_users.py --username amir --display "Amir" --persona frequent_bnpl` (idempotent) creates a user + `user_settings`. Isolation test: seed two users, write one row each through the repository, assert each sees one row. Add a minimal throwaway table-agnostic check if no domain table is wired yet — use `user_settings`.
- **Verify:** `uv run pytest tests/test_auth.py tests/test_user_isolation.py` passes; manual: `uvicorn` + `curl` login for a seeded user returns a token, `/api/auth/me` with it returns the user.

### Task 7 — Frontend skeleton
- **Files:** `frontend/` (create-next-app: TS, App Router, Tailwind, ESLint, no `src/`), `frontend/app/globals.css` (v1 tokens), `frontend/app/login/page.tsx`, `frontend/app/(app)/layout.tsx`, `frontend/app/(app)/page.tsx`, `frontend/lib/session.ts`, `frontend/components/layout/Nav.tsx`, `frontend/.env.example`.
- **Steps:** scaffold with the current create-next-app; copy v1 tokens and the Nav pattern; add TanStack Query provider; login page posts the username, stores the token in `sessionStorage`, redirects; `(app)` layout redirects to `/login` without a token; shell shows the display name and a logout button.
- **Verify:** `npm run build` and `npm run lint` pass; manual: login as a seeded user shows the shell; logout returns to `/login`.

### Task 8 — Generated API client
- **Files:** `frontend/lib/api/schema.d.ts` (generated), `frontend/lib/api/client.ts`, `frontend/package.json` scripts `gen:api` and `check:api`.
- **Steps:** read openapi-typescript and openapi-fetch docs first. `gen:api` fetches `${API}/openapi.json` (or reads an exported file written by `uv run python -m app.export_openapi`) and writes `schema.d.ts`. `client.ts` wraps `openapi-fetch` with the bearer token and the error envelope. `check:api` regenerates to a temp file and fails if it differs from the committed one.
- **Verify:** `npm run gen:api && npx tsc --noEmit` passes; change a response field in the backend, run `npm run check:api` → it fails; revert → passes.

### Task 9 — Test tooling
- **Files:** `frontend/vitest.config.ts`, `frontend/tests/unit/session.test.ts`, `frontend/playwright.config.ts`, `frontend/tests/e2e/login.spec.ts`.
- **Steps:** Vitest + Testing Library + jsdom; one unit test for the session helper. Playwright with a `webServer` config that starts the frontend; the smoke test assumes the backend is running with a seeded user (`PLAYWRIGHT_USERNAME`).
- **Verify:** `npm run test` passes; `npx playwright test` passes the login smoke test.

---

## What actually happened (deviations from the tasks above)

- **Task 2:** torch needed `--index pytorch-cpu=… --index-strategy unsafe-best-match` and a bounded `requires-python`; the 3.11 fallback was not needed.
- **Task 3:** `httpx2` is the dev dependency Starlette's `TestClient` wants; the module-level `app` is built lazily (and once) via module `__getattr__` so importing `app.main` never needs env vars; the project is installable (hatchling) so `scripts/` can `import app`.
- **Task 4:** money columns are `bigint` sen and links are composite `(id, user_id)` foreign keys (**D-26**); username check mirrors the app regex; default privileges revoked for future tables. `scripts/check_rls.py` was added (and needs the optional `SUPABASE_ANON_KEY`). **Not applied to any database yet.**
- **Task 5:** `ScopedTable.list` was renamed `list_rows` and pages past the 1000-row PostgREST cap; ids that are not UUIDs read as "not found". `tests/fakes.py` is a fake of the query builder, so the real repository code runs in unit tests; `tests/integration/` is the contract check against real Supabase (**not yet run**).
- **Task 6:** added a failed-login rate limiter (per peer address, IPv6 /64, bounded memory), 404/405 enveloping, CORS headers on 500, 503 on upstream outage, `SecretStr` secrets.
- **Task 7:** `create-next-app` produced Next 16.4 with Cache Components enabled; both flags were switched off (see the comment in `next.config.ts`). `frontend/.env.example` could not be written (permission rule).
- **Task 8:** `npm run gen:api` uses `uv run python -m app.export_openapi` (no server or env needed) rather than fetching `/openapi.json`.
- **Task 9:** Playwright runs the real FastAPI app on the in-memory DB (`backend/tests/e2e_server.py`, ports 8100/3100) instead of assuming a seeded Supabase user; it covers desktop Chrome and a Pixel 7 profile.

## Wrap-up (do not skip)

- [x] `refdocs/STATUS.md` — phase table updated, verification ledger updated with what was actually run
- [x] `refdocs/changelog/CHANGELOG.md` — session entry added
- [x] `refdocs/changelog/DECISIONS.md` — D-23 and D-15 resolved from the spike; D-26 added
- [~] `refdocs/guides/env_setup.md` updated; `backend/.env.example` could not be read or edited (permission rule) and `frontend/.env.example` could not be created — the author should check both against env_setup.md
- [x] README "Project layout" updated to the real tree (a file-structure doc becomes worthwhile once P1 adds the domain layer)
- [x] This doc updated to match what actually happened
- [ ] **Live-Supabase verification** (needs the author): apply `0001_init.sql`; `check_rls.py`; `seed_users.py`; `pytest -m integration`; manual login with `curl`
- [ ] Next: write `refdocs/plans/<date>-p1-ledger-bnpl.md` + its execution doc (`/plan-feature`)
