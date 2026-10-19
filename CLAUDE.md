# PaySense v3 — Claude Context

> Read this file at the start of every session, then run through `.claude/memory/preflight.md` — it's the six-question gate that turns these rules into something you actually did. PaySense v3 is an AI-driven decision support system that helps Malaysian university students make informed BNPL purchasing decisions by combining financial health forecasting with BNPL risk classification — forked from PaySense v2 (the UTP final-year project, commit `cdd43cf`) for the FinTechaton 2026 Shenzhen competition. v2 lives separately at `C:\Users\User\Documents\College\FYP\PaySense_v2` and is a read-only reference from this repo — never edit it from a v3 session. The competition-specific differences are recorded in the PRD and `internal/refdocs/changelog/DECISIONS.md`.
> The PRD is the source of truth; this file is the short operating brief; preflight is the gate. Keep all three short.

---

## Competition variant (FinTechathon 2026, Topic A)

This copy has its **own Supabase project** (`paysense-v3`); the FYP repo is frozen at tag `fyp-final` and never touched from here. Scope and order: `internal/refdocs/fintechathon-2026/work-packages.md`. Overrides, each with an ADR:
- **D-05 → D-47:** an assistant layer uses an LLM. The LLM **narrates and proposes; it never produces a score, forecast or amount**. Engine candidates are unchanged.
- **D-53:** the LLM is provider-agnostic: Gemini free tier first, Claude (Anthropic API) as the upgrade.
- **D-48:** three permission tiers; the model has **no write tool**; writes run only from a user-confirmed pending action.
- **D-03 → D-49:** login is hardened in this copy (passphrase factor, token revocation, quotas).
- **D-27 → D-50:** optional savings buffer in both engines (retrain, report old and new numbers).
- Rule 7 (no dates or deadlines in docs) **still applies** to repo docs.
- Cloud sessions push their own `claude/...` working branch; only the author merges and pushes `main`.

---

## Order of authority (when docs conflict, surface it — don't resolve silently)

**Public vs private.** `internal/` is gitignored and is its own private git repo: `internal/refdocs/` (PRD, status, decisions, plans, research, competition material) and `internal/pdfs/` (organiser PDFs, deck). Only `docs/` (technical documentation, honest limits, roadmap, demo scenario, deployment, env setup, file structure), `SECURITY.md` and the root files are public. Never link a public file to anything under `internal/`, and never copy private content into `docs/`.

0. `internal/refdocs/STATUS.md` — **where we are right now.** Phase checklist + the current module's progress. Check this first, every session.
1. `internal/refdocs/paysense-v3-PRD.md` — **what & why.** Owns scope, architecture, both engine designs, roadmap, Decision Log.
2. `internal/refdocs/changelog/DECISIONS.md` — **settled calls.** Read before re-debating an architectural choice.
3. `internal/refdocs/plans/*.md` — **what to build & why.**
4. `internal/refdocs/execution/*.md` — **how & in what order.**
5. `docs/` (public) and `internal/refdocs/guides/` — **operational reference.** `docs/env_setup.md` (every variable, where to get it), `docs/deployment.md`, `internal/refdocs/guides/checklist.md` (pre-ship).
6. `internal/refdocs/paysense-v3-sources.md` and `internal/refdocs/context/` — **raw research and founding context** (v1 lessons, research brief, academic constraints, BNPL billing rules).

If two docs disagree, stop and ask. Don't pick one and move on.

---

## Mandatory rules

### 1. Update the changelog after every session
After any session that changed code, made a decision, or modified a plan, add an entry to **`internal/refdocs/changelog/CHANGELOG.md`** (format is in that file). Do not skip. Even a one-line fix gets a one-line entry. Update `internal/refdocs/STATUS.md` in the same pass — the author relies on it as the single source of truth.

### 2. Plan before you build
Before implementing any non-trivial feature, a **plan doc** (`internal/refdocs/plans/`) and an **execution doc** (`internal/refdocs/execution/`) must exist. If they don't, create them before writing code (`/plan-feature`).

### 3. Log decisions as ADRs
New architectural/design decision → add an ADR to `internal/refdocs/changelog/DECISIONS.md` (Decision → Why → Rejected/Trade-off) and its one-liner to PRD §7 with the same id. Mark unresolved assumptions `ASSUMED:` and surface them at the next checkpoint.

### 4. Keep docs current
If you deviate from a plan during execution, update the execution doc to match reality. Stale docs are worse than no docs.

### 5. Test first, and say what you ran
Write the test before the implementation (TDD), target ≥ 80% coverage on `backend/app` and `frontend/lib`. Never say "done" or "passing" without naming the command you ran and its result.

### 6. Commits and pushes
Commit at the end of each verified task group with conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`, `perf:`). **Never push** — the author pushes. Never commit `.env*` or anything under `data/private/`.

### 7. No dates, deadlines or timeline talk
The author has asked that plans, docs and reports carry no schedule, deadline or checkpoint framing. Phases are ordered by dependency only. (Dates on changelog entries and file names are records, not deadlines — keep those.)

---

## The hard constraints (these are mechanism, not preference)

1. **This repo is public.** No real personal financial data and no secrets, ever (D-14). Real data lives only in gitignored `data/private/`; fixtures and personas are synthetic. The secret-guard hook blocks key literals at write time.
2. **Candidate algorithms are fixed by the literature review** (D-05): ARIMA / Prophet / LSTM for financial health forecasting; Random Forest / XGBoost / LightGBM for BNPL risk classification; SHAP for XAI. Only benchmarks (naive, moving average, logistic regression) and configurations (global LSTM, monotonic constraints, counterfactual search) may be added. Anything else needs a new ADR and the author's sign-off.
3. **Engine 2 features exist in exactly one place:** `backend/app/engines/risk/features.py` (D-09). `ml/` imports it; nothing re-implements a feature. Artefacts carry a feature-schema hash; the server refuses to start on a mismatch. Engine 2's label is Engine 1's simulated shortfall probability (D-07) — never a hand-written formula.
4. **Every database query is user-scoped** (D-03). Repository functions take `user_id` first; route handlers never build queries; every new query gets an isolation test.
5. **No fabricated numbers.** Every value on screen traces to a model, a simulation or the user's data. Evaluation tables and figures in `reports/` are regenerated by scripts, never hand-edited. Benchmarks are always in every comparison, and results are reported even when they are unflattering.
6. **v1 is read-only.** `../PaySense/` is a reference to port from. Never edit, commit or run migrations against it from a v2 session.
7. **Money is integer sen** in every calculation (D-16). Convert at the API boundary only.

---

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router) + TypeScript strict + Tailwind 4 + Recharts; TanStack Query; zod; API types generated from OpenAPI (`openapi-typescript` + `openapi-fetch`) |
| Backend | FastAPI + Pydantic v2, Python pinned via `uv` (`.python-version`), Ruff, pytest |
| ML | statsforecast (ARIMA, benchmarks), prophet, PyTorch (global LSTM; ONNX Runtime for serving if memory requires), scikit-learn / xgboost / lightgbm, shap, optuna, scipy |
| Database | Supabase Postgres (Singapore), accessed only by the backend with the service key; RLS on, no anon policies |
| Hosting | Vercel (frontend), Render (backend; Cloud Run fallback per D-15) |
| Tests | pytest + httpx; Vitest + Testing Library; Playwright |

## Surfaces

One product, three source trees. Frontend and backend share **no source** — only the HTTP contract, captured as generated types. `ml/` imports from `backend/app/engines/`; the backend never imports `ml/`.

| Tree | Root | Run | Can | Cannot |
|---|---|---|---|---|
| Backend API | `backend/app/` | `cd backend && uv run uvicorn app.main:app --reload --port 8000` | Serve the API, run both engines, talk to Supabase | Train models (it only loads artefacts) |
| Frontend | `frontend/` | `cd frontend && npm run dev` | Render screens, call the API through the generated client | Talk to Supabase, compute any score or forecast, hold provider rules (served by `GET /api/providers`) |
| Offline ML | `backend/ml/` | `cd backend && uv run python -m ml.<module>` | Generate synthetic data, evaluate candidates, train and export artefacts to `backend/models/`, write `reports/` | Be imported by `app/` |

**A backend route or schema change does nothing for the frontend until `npm run gen:api` is run** — the generated types are the contract.

## Running it

| What | Command | Notes |
|---|---|---|
| Backend dev server | `cd backend && uv run uvicorn app.main:app --reload --port 8000` | Created in P0; needs `backend/.env` |
| Backend tests | `cd backend && uv run pytest` | `-m integration` hits the real Supabase |
| Backend lint | `cd backend && uv run ruff check . && uv run ruff format --check .` | |
| Frontend dev server | `cd frontend && npm run dev` | Needs `frontend/.env.local` |
| Frontend checks | `cd frontend && npm run lint && npx tsc --noEmit && npm run test && npm run build` | |
| Regenerate API types | `cd frontend && npm run gen:api` | After any backend route/schema change |
| E2E | `cd frontend && npx playwright test` | Backend must be running with a seeded user |
| Seed a tester | `cd backend && uv run python scripts/seed_users.py --username <name> --display <Name> --persona <persona>` | Idempotent |

All of the above are created in P0; until then they don't exist.

---

## Build sequence

P0 Foundation → P1 Ledger & BNPL domain → P2 Synthetic population → P3 Engine 1 evaluation → P4 Engine 1 serving → P5 Engine 2 training → P6 Engine 2 serving → P7 Frontend → P8 Deployment → P9 UAT kit → P10 Optional (LLM phrasing). Frontend screens for a module may start once that module's backend phase is green. Full exit criteria: PRD §6.

**Never build the second of anything until the first is green end-to-end.**

---

## When blocked

- **Open question:** check the PRD's Open Questions section. If unresolved, write your assumption to `DECISIONS.md` as `ASSUMED:`, proceed, surface at the next checkpoint.
- **Doc conflict:** stop. Quote both passages and ask. Don't pick silently.
- **Ambiguous spec:** prefer the **more rigorous, more explainable** option — the one an internal examiner can defend and a tester can understand. Log the choice.
- **Needs the author** (Supabase credentials, a real provider checkout, supervisor sign-off): ask once, then keep building everything that doesn't depend on it.

---

*Companion brief to `internal/refdocs/paysense-v3-PRD.md`. Last updated: 2026-10-08.*
