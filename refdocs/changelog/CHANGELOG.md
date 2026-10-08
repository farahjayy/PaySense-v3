# PaySense v2 — Changelog

> Mandatory session log. Add an entry after **every** session where code changed, a decision was made, or a plan was modified. Newest first. Even a one-line fix gets a one-line entry.

Entry format:
```
### YYYY-MM-DD — [short summary of session goal]
- **Changed:** what files/components were touched and why
- **Decided:** any architectural or design decisions and the reasoning
- **Deviations:** anything that differed from the plan, and why
- **Verified:** what was actually run, and the result (not "should work")
- **Known issues / next steps:** what was left open
```

Those five lines are the floor, not the ceiling. Add these when the session earns them — a debugging session in particular is unreadable without the first two:
- **Reported:** the symptom in the user's own words, before you knew the cause
- **Diagnosed:** what you found, and how you proved it — the reproduction, not the hypothesis
- **Trade-off:** what this change costs, and who it costs it to
- **Noted, not changed:** something you found and deliberately left alone, so the next session doesn't re-investigate it

Rules that make this file worth keeping:
- **"Verified" means a command was run.** Name it and give the result. If nothing was run, write "nothing verified this session" — that is useful information.
- **Deviations are the most valuable line.** A plan that changed silently is a plan nobody will trust next time.
- **Write what you learned, not what you touched.** "Fixed the player" ages into nothing. "The provider's iframe navigates the top context, which sandbox flags block" is still worth reading in six months.
- Don't rewrite history. Corrections go in a new entry that references the old one.

---

## [Unreleased]

### 2026-10-08 — P0 Foundation built (live-Supabase steps still pending)
- **Changed:** Created `backend/` (uv project, FastAPI app factory, settings, error envelope, username login, user-scoped repository base, seed/RLS-check/OpenAPI-export scripts, migration `0001_init.sql`, 110 tests + 9 integration tests), `frontend/` (Next.js 16 shell: login, auth gate, app shell, typed client, 26 unit tests, Playwright journey), `reports/spikes/p0-dependency-spike.md`. Edited D-15, D-23, new D-26 in DECISIONS/PRD §7; PRD §1, §8; `env_setup.md`; STATUS.
- **Decided:** D-23 → Python **3.12** (all wheels install). D-15 → torch alone takes a process to ~607 MB, so **the backend never imports torch; the LSTM is served via ONNX Runtime** (P3/P4 must add the export + parity test). New **D-26** → money columns are `bigint` sen and every cross-table link is a composite `(id, user_id)` foreign key. Cache Components left off in Next (`next.config.ts` comment says why).
- **Diagnosed:**
  - Reported by review, confirmed by test: Supabase silently caps a select at 1000 rows, so an unbounded `ScopedTable.list` would hand the engines a truncated ledger and produce plausible wrong numbers. The fake now enforces the cap; `list_rows` pages internally (test with 1,500 rows).
  - Behind Render's proxy the login rate limiter would key on the proxy IP (everyone shares one bucket) — and `--forwarded-allow-ips='*'` would let clients spoof `X-Forwarded-For` to dodge it. Fixed by keying on the peer address only and documenting the uvicorn flags in `env_setup.md`.
  - `ServerErrorMiddleware` sits outside `CORSMiddleware`, so a 500 reached the browser as an opaque CORS failure; the 500 handler now adds the CORS header itself.
- **Trade-off:** username-only login (D-03) means the rate limiter is the only brute-force control; it is per-process, so deployment must run a single worker. The 401 reveals whether a username exists (accepted for a 5–7-person UAT).
- **Deviations from the execution doc:** (1) money stored as sen, not `numeric(12,2)` (D-26); (2) `provider_limits` has no `id`, so it gets its own module rather than `ScopedTable`; (3) `app.export_openapi` added so `gen:api` needs no running server or credentials; (4) `tests/e2e_server.py` added so Playwright runs against the real app on an in-memory DB — the smoke test therefore does **not** touch Supabase; (5) `frontend/.env.example` not created (a permission rule blocks writing `.env*`); (6) `@types/node` 24 instead of 20 (Vitest 5 peer requirement); (7) the dev dependency `httpx2` is Starlette's required test-client package, not an app dependency.
- **Verified:** see STATUS verification ledger — backend `pytest` 110 passed / 95% coverage, ruff clean; frontend lint, tsc, 26 Vitest tests, build, `check:api` (proved to fail on drift); Playwright 6 passed on desktop and Pixel 7 against the **in-memory** backend. **Not verified:** the migration has not been applied to any database (SQL only parsed with pglast); `check_rls.py`, `seed_users.py` and the 9 `-m integration` tests have not run against Supabase.
- **Noted, not changed:** `npm audit` flags dev-only ESLint-toolchain packages; nothing ships to the browser from them. Memory figures are Windows import-and-toy-workload RSS, not the real served stack.
- **Known issues / next steps:** author creates the Supabase project and applies the migration (see STATUS "Right now"); then run the three live checks. Next phase: P1 — write its plan + execution pair first. Frontend review (react-reviewer) was still running when this entry was written.

### 2026-10-08 — Provider list narrowed to three named providers (D-24 revised)
- **Changed:** PRD §4 (BNPL plans row), §7 (D-24), §8 (Q6); DECISIONS D-24; STATUS known gaps; kickoff superprompt.
- **Decided:** only SPayLater, TikTok PayLater and Atome are named and rule-driven; every other provider uses a manual "Other provider" entry where the user types the first payment date, instalment count and the checkout instalment amount (or total payable). Supersedes the scaffold-time wording that listed Grab PayLater and Boost PayFlex as "unverified" providers.
- **Why:** naming a provider implies the app understands its rules, and a flat monthly fee rate can't represent Boost's or Grab's fees; a typed checkout amount is more accurate.
- **Verified:** nothing verified this session (documentation only).
- **Known issues / next steps:** none new; the P1 plan must implement the "Other provider" form and schedule-from-entered-amount path.

### 2026-10-08 — Project scaffolded
- **Changed:** Created the project doc system — `refdocs/` (PRD, STATUS, sources, context/ ×4, guides/, changelog/DECISIONS, plans/, execution/), `CLAUDE.md`, `README.md`, `.gitignore`, `.env.example` files, `.claude/` (settings, secret-guard hook, agents, commands, memory/preflight), and the kickoff superprompt. No application code yet.
- **Decided:** D-01 to D-25 (PRD §7). Load-bearing: component forecaster with Monte Carlo (D-04); candidates stay within the literature review, with benchmarks and monotonic constraints added (D-05, superseding an earlier "add Chronos + EBM" choice after the author asked for a recommendation); Engine 2 label = Engine 1's simulated shortfall probability (D-07); one shared feature module with a schema hash (D-09); username-only login (D-03, supervisor decision); no real personal data in this public repo (D-14); verified vs unverified BNPL providers (D-24); Berka as a benchmark only (D-25). UAT ethics approval not required (author).
- **Verified:** Nothing to verify — no code exists yet.
- **Known issues / next steps:** Five `ASSUMED:` items open (DECISIONS.md); P0's dependency spike resolves the Python-version and memory ones. Next session starts from `refdocs/plans/2026-10-08-p0-foundation.md`.
