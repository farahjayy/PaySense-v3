# Plan — P1 Ledger & BNPL domain

> Phase P1 of `refdocs/paysense-v2-PRD.md` §6. Execution doc: `refdocs/execution/2026-10-08-p1-ledger-bnpl.md`.
> A plan says **what and why**. The execution doc says **how and in what order**.

## Why this exists

Everything the engines do rests on three things being right and boring: the **instalment schedule** (a wrong first due date creates phantom missed payments and moves money into the wrong month of the simulation, which is Engine 2's label), the **ledger** (what counts as income, spend, refund or transfer decides the series Engine 1 forecasts), and the **limit rule** (D-28: a purchase above a provider's remaining limit is part-paid at checkout). v1 already got the schedule and ledger maths right and pinned them with tests; P1 ports them, bends them to the v2 decisions, and puts a user-scoped API in front of them. No ML in this phase.

## What changed since the roadmap was written (read before building)

- **D-27: no balance.** v1's ledger-mode maths (`ledger.py`, `transaction_ops.py`, balance adjustment in `plans.py`) existed only to keep a balance in step. v2 stores none, so those functions are **not ported**, balance sync/`GET /api/balance` do not exist, and the dashboard's "balance" becomes a **month summary** (income / expense / net per month). This also removes the multi-write consistency risk (no balance to drift) — what remains is "insert the logged payment, then mark the instalment paid", compensated by deleting the payment if the second write fails.
- **D-28: limits cap financing.** `financed = min(price, remaining limit)`; the excess is a **checkout payment** in the purchase month. The remaining limit and how a fee interacts with the cap are `ASSUMED` (see PRD §8 Q9) until the author supplies a real checkout.
- **D-24:** only SPayLater, TikTok PayLater and Atome are rule-driven; everything else is the manual "Other provider" path.
- **D-26:** money is `bigint` sen in the database. This plan proposes how it crosses the API (D-29, below).

## What's already covered (no work needed)

- `ScopedTable` (user isolation, 1000-row paging, UUID guards), `fakes.py`, the error envelope, `current_user`, `ErrorEnvelope` OpenAPI responses, the typed-client pipeline (`npm run gen:api` + drift check). P1 builds on them; it does not re-create them.
- Tables for transactions, recurring items, plans, installments, provider limits, risk checks exist in `migrations/0001_init.sql` (unapplied; edited in place until the author applies it — afterwards changes are `0002_*.sql`).

## Scope

**In — pure domain (no database; first):**
- `domain/money.py`: sen helpers (decimal-text ↔ sen with no float multiplication).
- `domain/providers.py`: the four provider entries (D-24) as frozen data, served by the API (D-17).
- `domain/schedule.py`: port of v1 `schedule.py` in sen end to end, plus the **limit split** (D-28) and the **manual "Other provider" schedule** (typed first date, count, instalment amount or total payable; exact split; leftover sen in the last instalment).
- `domain/categorize.py`: port (word-boundary matching), plus reserved categories `Refund` and `Transfer`.
- `domain/flows.py`: classify a transaction as `income | spend | refund | transfer | savings` (the one definition Engine 1 and the month summary share); `months_of_history`; `month_summary`.
- `domain/plans.py`, `domain/bills.py`: status derivation, enrichment, monthly bills — ported, sen-based, with the used-limit calculation.
- `domain/csv_import.py`: parse a bank/persona CSV into preview rows (date, amount in sen, type guess, category guess, issues, duplicate flag), skipped rows with reasons.

**In — persistence and API:**
- Repositories on `ScopedTable`: transactions, recurring items, plans + installments, provider limits, user settings (onboarding state).
- Routes: `GET /api/providers`; provider limits (`GET`/`PUT`/`DELETE`); transactions CRUD + list; `POST /api/import/csv` (preview, stateless) and `POST /api/import/confirm`; `GET /api/summary/months`; recurring items CRUD (manual only — detection is P4); plans (`preview`, create, list, get, rename, delete with keep/delete of logged payments, mark paid single/bulk); `GET /api/bills`.
- OpenAPI regenerated and `schema.d.ts` committed.

**Out (and why):** recurring *detection* (P4); any forecast or risk endpoint (P4/P6); frontend screens beyond what P0 has (P7 — but the contract is generated now); PDF import and bank APIs (out of scope, D-13); balance of any kind (D-27).

## Proposed decisions (ADR D-29, written when the first API task lands)

1. **Money over the wire is integer sen** (`amount_sen`, `total_price_sen`, …), never floating-point RM and never decimal strings. D-16's "convert at the API boundary" is read as "convert at the *presentation* boundary": the frontend formats sen as `RM 1,234.56` and parses what the user types with a decimal-text function (`lib/money.ts`), so no float ever touches a ringgit amount. Rejected: RM floats (v1; rounding), RM decimal strings (every client must parse them; no benefit over sen).
2. **Refunds and transfers use two reserved categories**, `Refund` and `Transfer` — no schema change. A `Refund` is stored as income but never counts as income: it is netted against spend in its week. A `Transfer` (own-account moves, e-wallet top-ups) is excluded from every flow in both directions. `flows.classify` is the only place this is decided. Rejected: negative amounts (the `amount_sen > 0` invariant is load-bearing), a new column (not needed yet).
3. **Import is stateless.** Preview returns rows; confirm receives the user's edited rows and re-validates them. Nothing is held server-side between the two calls (Render sleeps and restarts; v1's in-memory preview store would lose uploads). Duplicates of already-stored transactions are flagged in the preview and unchecked by default.

## Approach

1. Pure domain first, test-first, ported v1 tests re-expressed in sen and re-run green before anything is built on them. This part needs neither the database nor the author.
2. Add the plan columns for D-28 (`financed_sen`, `upfront_sen`) to the migration while it is still unapplied.
3. Repositories with fake-backed tests, **every function with an isolation test**, plus matching `-m integration` contract tests that run once Supabase credentials exist.
4. Routes thin: validate, call a repository or domain function, shape the response. No queries in handlers.
5. Regenerate types last and commit them.

## Risks & unknowns

| Risk / unknown | Confidence | Mitigation |
|---|---|---|
| How a real provider applies the limit to price vs price + fee, and how it counts used limit (D-28, `ASSUMED`) | Low — needs a real checkout | Implement as a single named function with the assumption in its docstring; the author supplies one real example; one test pins it |
| Mark-paid is two writes without a database transaction | Medium | Insert the payment first, then mark paid; on failure delete the payment and surface the error; an integration test forces the second write to fail |
| Bank/persona CSV formats vary (debit/credit columns, dd/mm/yyyy, `RM` and parentheses) | Medium | Port v1's heuristics; table-driven tests from real-shaped samples; every unparseable row is reported, never dropped silently |
| Duplicate imports double the history and distort Engine 1 | High | Fingerprint dedupe in the preview (test with a re-import) |
| Ported v1 tests assume floats | High | Re-express in sen; keep the same cases so the port is demonstrably behaviour-preserving |
| `provider_limits` has no `id` so `ScopedTable` does not fit | High | Own small repository module keyed by `(user_id, provider)` |

## Definition of done

Every line below is true and has been *observed*:

- `cd backend && uv run pytest` passes, including: schedule maths (exact-sum, leftover sen, month-end clamping), the limit split (limit RM200 + price RM300 → RM100 at checkout, RM200 financed, with and without a fee), the manual-provider path, CSV parsing (incl. a re-import flagged as duplicates), and an **isolation test for every repository function**; `uv run ruff check .` clean; coverage ≥ 80% on `app/`.
- Each endpoint has a round-trip test through the HTTP client against the fake; each user-owned endpoint has a two-user test proving the other user's id returns 404, not 403 and not the row.
- `npm run gen:api && npm run check:api && npx tsc --noEmit && npm run lint && npm run test && npm run build` pass with the regenerated types.
- `pytest -m integration` for the new repositories passes against the real Supabase project **once the author has provided credentials** — until then P1 stays 🔶 and the ledger says so.
