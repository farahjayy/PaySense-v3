# Preflight — PaySense v3 Session Start

> Read this at the start of every session, before touching code.
> One page, six questions, then you can build. CLAUDE.md is the reference; this is the gate.

---

## 1. Where are we?

Open `internal/refdocs/STATUS.md`. Find the current phase and the one next action.
If STATUS's claims and the code disagree, **that's the session's first task** — not the thing you were about to do.

---

## 2. Which tree am I about to touch?

| Tree | Root | Touching it means… |
|---|---|---|
| Backend API | `backend/app/` | Route/schema change → regenerate frontend types. New query → `user_id` first + isolation test. |
| Engines | `backend/app/engines/forecasting/`, `backend/app/engines/risk/` | Shared by serving **and** `ml/`. A change here can invalidate trained artefacts. |
| Offline ML | `backend/ml/` | Imports engines; never imported by `app/`. Outputs go to `backend/models/` and `reports/` by script only. |
| Frontend | `frontend/` | Uses only the generated client; computes no scores; holds no provider rules. |
| v1 | `../PaySense/` | **Read-only.** Copy from it, never write to it. |

The frontend and backend share no source — only the generated API types. They do not sync on their own.

---

## 3. Does a plan exist for what I'm about to build?

Non-trivial feature → a plan doc in `internal/refdocs/plans/` **and** an execution doc in `internal/refdocs/execution/`.
If neither exists, write them first (`/plan-feature`). If one exists but reality has moved, update it before building on it.

---

## 4. Has this already been decided?

Skim `internal/refdocs/changelog/DECISIONS.md` before re-opening an architectural choice. If your plan contradicts an ADR, you need a new ADR that says why — not a silent reversal. In particular: candidate algorithms (D-05), the Engine 2 label (D-07), the single feature module (D-09), username-only login (D-03).

Check the open `ASSUMED:` list at the bottom of that file. If today's work is load-bearing on one of them, **confirm it before you build**, not after.

---

## 5. Did I change one half of a pair without the other?

PaySense has three pairs that break silently, because the first half compiles and passes its own tests:

| If I changed… | …I must also | Enforced by |
|---|---|---|
| An Engine 2 feature in `engines/risk/features.py` | Regenerate the dataset, retrain, export a new artefact version whose `metadata.json` carries the new feature-schema hash | Startup hash check refuses a mismatched artefact (D-09) |
| A backend route or Pydantic schema | Run `pnpm gen:api` and commit the regenerated `frontend/lib/api/schema.d.ts` | `pnpm check:api` fails on drift (D-18) |
| A DB column or table | Add a numbered migration in `backend/migrations/`, update the repository function and the Pydantic schema | Repository tests; checklist "API contract changes" |

And the one that is never mechanical: **is any real personal data about to enter this public repo?** If a file came from `data/private/`, a real statement, or the v1 author's spreadsheets — stop.

---

## 6. Will I close the session properly?

`/session-end` — changelog entry, STATUS phase table, verification ledger, any new ADR.
The changelog entry is mandatory after any session that changed code, made a decision, or modified a plan. Even a one-line fix gets a one-line entry.

---

## Quick links

| Doc | Purpose |
|---|---|
| `internal/refdocs/STATUS.md` | Where the build actually is |
| `CLAUDE.md` | Operating brief — rules, constraints, stack |
| `internal/refdocs/paysense-v3-PRD.md` | Scope, both engine designs, roadmap, decision log |
| `internal/refdocs/changelog/DECISIONS.md` | Settled calls — read before re-debating |
| `docs/env_setup.md` | Every env var, where to get it |
| `internal/refdocs/guides/checklist.md` | Pre-ship checklist |
| `internal/refdocs/plans/` · `internal/refdocs/execution/` | What/why · how/in what order |
| `internal/refdocs/context/` | v1 lessons, research brief, academic constraints, billing rules |
