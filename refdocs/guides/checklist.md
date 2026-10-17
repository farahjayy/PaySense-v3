# Pre-Ship Checklist — PaySense v3

> Run the relevant section before pushing, deploying, or calling a phase done.
> Not every item applies to every change — use judgement based on what actually changed. But read the list; that's where you notice the thing you forgot.
> The commands below are the ones P0 creates. Until P0 is done, they don't exist yet — say so rather than pretending they passed.

---

## Every change

- [ ] **It was actually run.** Not "it compiles" — executed, and the result observed. If it wasn't run, say so rather than implying otherwise.
- [ ] **Build passes** — `cd frontend && npm run build`
- [ ] **Tests pass** — `cd backend && uv run pytest` and `cd frontend && npm run test`
- [ ] **Lint/type check clean** — `cd backend && uv run ruff check . && uv run ruff format --check .` and `cd frontend && npm run lint && npx tsc --noEmit`
- [ ] **No secrets staged** — `git status` shows no `.env*`; no key literal in the diff
- [ ] **No real personal data staged** — nothing under `data/private/`, no `.xlsx` of real transactions, no real names/amounts in fixtures (this repo is public — D-14)
- [ ] **No stray debug output** left in the diff — `console.log`, `print`, commented-out experiments
- [ ] **Changelog entry added** — `refdocs/changelog/CHANGELOG.md`, including an honest **Verified** line
- [ ] **STATUS.md reflects reality** — the phase table doesn't round up, and the verification ledger has a row for what you just ran
- [ ] **Docs match what you built** — if the work diverged from the execution doc, that doc is edited, not left stale

---

## Model or feature change (Engine 1 / Engine 2)

- [ ] Feature defined only in `backend/app/engines/risk/features.py`; `ml/` imports it (D-09)
- [ ] Feature list changed → dataset regenerated, model retrained, new artefact version, `metadata.json` hash updated, startup hash check passes
- [ ] Evaluation reran on the same splits/seeds; `reports/` tables regenerated, not hand-edited
- [ ] Designed-case tests still pass (academic-constraints §5)
- [ ] No candidate algorithm added outside D-05 without a new ADR

---

## New dependency

- [ ] Recorded in `refdocs/paysense-v3-sources.md` with its license and why it was chosen
- [ ] License is compatible with this project's distribution (public repo; avoid AGPL for served code)
- [ ] Its actual docs/types were read — the API was not recalled from memory
- [ ] Considered-and-rejected alternatives noted, so nobody re-derives that comparison
- [ ] Backend memory re-measured if it is a served dependency (D-15)

---

## New environment variable

- [ ] Added to `refdocs/guides/env_setup.md` with where to get it
- [ ] Added to `.env.example` with a blank/fake value
- [ ] Set in the deploy target's dashboard, if there is one
- [ ] Missing-variable case fails loudly at startup, naming the variable

---

## Architectural decision

- [ ] ADR in `refdocs/changelog/DECISIONS.md` — Decision → Why → Trade-offs/rejected
- [ ] Same id added to the PRD's §7 Decision Log
- [ ] Any `ASSUMED:` it resolves is deleted from the assumptions list

---

## Before deploy (Vercel + Render + Supabase)

- [ ] Migrations applied to the Supabase project in order; RLS enabled on every table
- [ ] Render env vars set (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SESSION_SECRET`, `CORS_ORIGINS` incl. the Vercel URL)
- [ ] Vercel `NEXT_PUBLIC_API_BASE_URL` = the Render URL, then redeploy
- [ ] Served model artefacts present and the feature-hash check passes on boot
- [ ] Backend resident memory under the host limit after one forecast + one risk check
- [ ] Fresh-session walkthrough on the live URL: login → import persona CSV → dashboard → risk check → confirm → plan → risk report; repeat on a phone browser
- [ ] Two tester accounts cannot see each other's data on the live deployment
- [ ] Supabase keep-alive plan in place (free projects pause after a week idle)

---

## API contract changes

- [ ] Backend route or schema changed → `cd frontend && npm run gen:api` run and the generated types committed in the same change (D-18)
- [ ] DB column added/changed → new numbered migration in `backend/migrations/`, repository layer and Pydantic schema updated together
- [ ] New query → takes `user_id`; an isolation test covers it (D-03)
