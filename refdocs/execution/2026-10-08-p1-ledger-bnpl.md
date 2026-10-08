# Execution — P1 Ledger & BNPL domain

> Plan: `refdocs/plans/2026-10-08-p1-ledger-bnpl.md`. Tasks run top to bottom. Each task carries its own **Verify** step; a task is not done until its Verify actually passes.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4).

## Before starting

- Read `CLAUDE.md`, `.claude/memory/preflight.md`, `refdocs/STATUS.md`, PRD §3.2 and §4, and ADRs D-16, D-17, D-24, D-26, D-27, D-28 (D-19 is **superseded** — do not implement balances).
- v1 reference (read-only), in `C:\Users\User\Documents\College\FYP\PaySense\backend`: `app/providers.py`, `app/services/{schedule,plans,bills,categorize}.py`, `app/routers/imports.py` (CSV path only), `tests/test_{schedule,plans,categorize,bills}.py`. **Not ported:** `ledger.py`, `transaction_ops.py`, balance adjustment in `plans.py` (D-27), PDF import.
- Conventions already in place: `ScopedTable` (`list_rows`, `get`, `insert`, `update`, `delete`), `tests/fakes.py`, `ErrorEnvelope` responses (`ERROR_RESPONSES`), `CurrentUser` / `DbDep` dependencies, `create_app(settings, db=...)`. Plain `def` handlers.
- Domain code is **pure**: no database, no clock (take `today` as a parameter), no float money.
- Tasks marked **[needs author]** cannot be verified without Supabase credentials or a real checkout example.

---

## Part A — pure domain (no database, no author)

### Task A1 — Money helpers
- **Files:** `backend/app/domain/__init__.py`, `backend/app/domain/money.py`, `backend/tests/domain/test_money.py`.
- **Steps (tests first):** `parse_rm("12.5") -> 1250`, `"1,234.56"`, `"RM 12"`, `"(12.00)"` → rejected (sign is handled by the caller), more than 2 decimals rejected, `""`/`"abc"` rejected with `ValueError`; all via `Decimal` of the *text* — never `float()`. `format_rm(123456) -> "RM 1,234.56"`. `percent_to_hundredths("1.5") -> 150` (rounded half up to 0.01%).
- **Verify:** `cd backend && uv run pytest tests/domain/test_money.py` passes; a grep shows no `float(` in `app/domain/`.

### Task A2 — Providers as data
- **Files:** `backend/app/domain/providers.py`, `backend/tests/domain/test_providers.py`.
- **Steps:** frozen `ProviderConfig(key, label, checkout_instalments, start_rule, start_offset_months, monthly_fee_applies, rule_driven)` for `spaylater`, `tiktok_paylater`, `atome`, `other` (D-24; keys match the migration's check constraint). `get_provider(key)` falls back to `other`. Tests pin each provider's rule (SPayLater/TikTok: first bill one month after purchase, nothing at checkout; Atome: first instalment on purchase date; `other`: rule_driven False). A test asserts the key set equals the migration's `provider` check list so they cannot drift.
- **Verify:** `uv run pytest tests/domain/test_providers.py`.

### Task A3 — Schedule, limit split, manual schedule
- **Files:** `backend/app/domain/schedule.py`, `backend/tests/domain/test_schedule.py`.
- **Steps:** read v1 `tests/test_schedule.py` (176 lines) and re-express **every case** in sen (same inputs, same expectations — this proves the port preserves behaviour). Port `total_payable_sen`, `split_sen`, `add_months` (clamps month ends), `default_first_payment_date`, `build_schedule` returning a list of frozen `Instalment(seq, due_date, amount_sen, paid_at_checkout)`. Then add, test-first:
  - `split_for_limit(price_sen, remaining_limit_sen | None, monthly_rate_pct, n) -> LimitSplit(financed_sen, upfront_sen)` implementing D-28: no limit → all financed; else the largest financed principal whose **total payable including fee** fits the remaining limit (binary search over `0..price`; `total_payable_sen` is monotone), `upfront = price − financed`. Cases: limit RM200 / price RM300 / no fee → RM200 financed, RM100 upfront; same with 1.5% × 6 months → financed principal is the largest p with p×1.09 ≤ RM200 (≈ RM183.48), upfront the rest; limit ≥ price → no upfront; limit 0 → financed 0 (caller rejects with `limit_exhausted`).
  - `build_manual_schedule(first_payment_date, n, instalment_sen=None, total_payable_sen=None)` for the "Other" provider: exactly one of the two amounts; equal instalments, or `split_sen` of the total with leftover sen last; every amount > 0; dates by `add_months`; `paid_at_checkout` always False; no fee, no provider rule.
- **Verify:** `uv run pytest tests/domain/test_schedule.py` — all ported cases plus the new ones; a property-style test over a grid of prices/rates/counts asserts the instalments always sum to the total exactly.

### Task A4 — Categorisation and reserved categories
- **Files:** `backend/app/domain/categorize.py`, `backend/tests/domain/test_categorize.py`.
- **Steps:** port v1 (word-boundary prefix matching: "rent" matches "rental" not "parents"; `guess_type` sign-then-keyword). Add reserved categories `REFUND = "Refund"`, `TRANSFER = "Transfer"` with keywords (refund, reversal, cashback → Refund; transfer, "own account", top up, topup, reload → Transfer); transfer/refund keywords must win over the generic ones in the same description. Re-express v1's `tests/test_categorize.py`.
- **Verify:** `uv run pytest tests/domain/test_categorize.py`.

### Task A5 — Flow classification, month summary, history length
- **Files:** `backend/app/domain/flows.py`, `backend/tests/domain/test_flows.py`.
- **Steps (tests first, then pure functions over plain dicts/dataclasses):**
  - `classify(txn) -> Flow` where `Flow` ∈ `income | spend | refund | transfer | savings`: `Transfer` category → `transfer` (excluded both ways); `Refund` category → `refund`; type `savings` → `savings`; else income/expense by type. This is **the only place** the rule lives (Engine 1 imports it in P4).
  - `month_summary(txns) -> list[MonthSummary(month, income_sen, spend_sen, net_sen, refund_sen, savings_sen)]` per calendar month, ascending; refunds net against that month's spend (spend never below 0); transfers ignored; `net = income − spend`.
  - `history_span(txns, today) -> HistorySpan(first_date, last_date, distinct_months, span_days)`; `distinct_months` = calendar months containing at least one non-transfer transaction. (The 4-month **gate** is applied in P4; P1 only supplies the number.)
- **Verify:** `uv run pytest tests/domain/test_flows.py`, including: a refund in the same month reduces spend, never creates income; a transfer changes nothing; an empty list returns an empty summary and a `None` span.

### Task A6 — Plan status, enrichment, used limit, monthly bills
- **Files:** `backend/app/domain/plans.py`, `backend/app/domain/bills.py`, `backend/tests/domain/test_plans.py`, `backend/tests/domain/test_bills.py`.
- **Steps:** port `derive_status`, `enrich_plan` (sen: `installment_amount_sen`, `total_payable_sen` = sum of the real instalments, `paid_count`, `remaining_count`, `next_due_date`), `monthly_bills` (current month first only if something is due; no synthetic RM0 row; then past descending, then future ascending). Add `used_limit_sen(plans_for_provider)` = sum of unpaid instalment amounts (**ASSUMED**, D-28 — one named function, docstring states the assumption). Re-express v1 `tests/test_plans.py` and `tests/test_bills.py` in sen.
- **Verify:** `uv run pytest tests/domain/test_plans.py tests/domain/test_bills.py`.

### Task A7 — CSV import parsing
- **Files:** `backend/app/domain/csv_import.py`, `backend/tests/domain/test_csv_import.py`, `backend/tests/domain/fixtures/*.csv` (small, **synthetic** samples only — no real statements, D-14).
- **Steps:** read v1 `routers/imports.py` lines 1–140 for the heuristics. Implement with the stdlib `csv` module (no pandas): header detection (date / description / amount / debit / credit, English and Malay aliases), dates `dd/mm/yyyy` first then ISO, amounts with `RM`, thousands commas and `(parentheses)`, sign → type, unsigned single amount → expense + issue "no sign on amount", ragged lines → skipped rows with reasons (never silently dropped), 5 MB / 5,000-row limits. `parse_csv(text) -> ImportPreview(rows, skipped)` where each row has `row, date, amount_sen, type, category_guess, description, issues, fingerprint`; `fingerprint(row)` = hash of (date, amount_sen, type, normalised description). `flag_duplicates(rows, existing_fingerprints)` marks rows already stored.
- **Verify:** `uv run pytest tests/domain/test_csv_import.py` with fixtures for: debit/credit columns, signed amounts, parentheses negatives, `RM1,234.50`, bad date, zero amount, ragged line, oversize input, and a **re-import**: parsing the same file twice and passing the first result's fingerprints marks every row of the second as a duplicate.

---

## Part B — schema and repositories (fake-backed; integration tests wait on the author)

### Task B1 — Plan columns for D-28 (migration still unapplied)
- **Files:** `backend/migrations/0001_init.sql`, `backend/migrations/README.md`, `backend/tests/fakes.py` (only if defaults are needed).
- **Steps:** while `0001` is unapplied, add to `bnpl_plans`: `purchase_date date not null`, `financed_sen bigint not null check (financed_sen > 0)`, `upfront_sen bigint not null default 0 check (upfront_sen >= 0)`, and `check (financed_sen + upfront_sen = total_price_sen)`. For manual ("other") plans `financed_sen = total_price_sen` and `upfront_sen = 0`. **If the author has already applied 0001, write `0002_plan_financing.sql` instead and never edit 0001.** Re-run the pglast syntax check.
- **Verify:** `uv run --no-project --with pglast python -I <parse script> migrations/0001_init.sql` parses; `git diff` shows the three columns and the check. **[needs author]** to apply.

### Task B2 — Transactions repository
- **Files:** `backend/app/db/transactions.py`, `backend/tests/test_transactions_repo.py`.
- **Steps:** thin functions over `ScopedTable("transactions")` taking `user_id` first: `list_between(db, user_id, start, end, *, type=None, category=None)`, `get`, `create`, `update`, `delete`, `bulk_create(db, user_id, rows)` (chunked inserts of ≤ 500), `fingerprints(db, user_id)` for dedupe, `list_for_plan`, `delete_for_plan`. Validate `amount_sen > 0`, `type`, ISO dates in Python before the database does.
- **Verify:** `uv run pytest tests/test_transactions_repo.py` — **an isolation test per function** (user B cannot read, update or delete user A's row; `bulk_create` stamps the caller's id even if rows carry another).

### Task B3 — Recurring items repository (manual CRUD)
- **Files:** `backend/app/db/recurring_items.py`, `backend/tests/test_recurring_repo.py`.
- **Steps:** `list_items`, `get`, `create` (`origin='manual'`), `update`, `delete`; `custom` cadence requires `custom_interval_days`. Deleting an item unlinks (not deletes) its transactions — matching the migration's `on delete set null`.
- **Verify:** `uv run pytest tests/test_recurring_repo.py` with an isolation test per function.

### Task B4 — Plans repository
- **Files:** `backend/app/db/plans.py`, `backend/tests/test_plans_repo.py`.
- **Steps:** `create_plan(db, user_id, plan, instalments)` inserts the plan then its instalments; **on any failure it deletes the plan (cascade removes instalments) and re-raises**. `list_with_instalments`, `get_with_instalments`, `rename`, `delete(keep_payments: bool)` (default keep: unlink; otherwise delete linked transactions first), `mark_paid(db, user_id, plan_id, seq, paid_date)` which **inserts the linked expense transaction first, then flips the instalment; if the flip fails it deletes the transaction and re-raises**, `mark_paid_many`. Logged payment: category `BNPL`, `is_bnpl=True`, `bnpl_plan_id` set, description `"{provider_label} instalment {seq}/{n} — {item}"`.
- **Verify:** `uv run pytest tests/test_plans_repo.py` — isolation per function; a test whose fake raises on the second write proves the compensation (no orphan payment, no half-created plan); marking the same instalment twice is rejected, not double-logged.

### Task B5 — Provider limits repository
- **Files:** `backend/app/db/provider_limits.py`, `backend/tests/test_provider_limits_repo.py`.
- **Steps:** keyed by `(user_id, provider)` — no `id`, so no `ScopedTable`: `list_limits`, `upsert_limit`, `delete_limit`. Extend `tests/fakes.py` with the `provider_limits` composite key if needed.
- **Verify:** `uv run pytest tests/test_provider_limits_repo.py` — isolation per function; upsert twice leaves one row.

### Task B6 — Integration contract tests for the new repositories **[needs author]**
- **Files:** `backend/tests/integration/test_p1_repositories.py`.
- **Steps:** mirror the isolation and compensation tests against real Supabase: cross-user plan link rejected by the composite foreign key, the new check constraint (`financed + upfront = total`), unique `(plan_id, seq)`, provider-limit upsert.
- **Verify:** `uv run pytest -m integration` passes once `backend/.env` exists. Until then the task stays open and the ledger says so.

---

## Part C — API

### Task C1 — Contract conventions, providers and limits routes
- **Files:** `backend/app/api/schemas.py` (extend), `backend/app/api/providers.py`, `backend/app/api/provider_limits.py`, `backend/app/main.py` (register routers), `backend/tests/test_providers_api.py`, `refdocs/changelog/DECISIONS.md` + PRD §7 (ADR **D-29**: money over the wire is integer sen; refunds/transfers are reserved categories; import is stateless).
- **Steps:** `GET /api/providers` (public rules, no auth needed? — **requires auth like everything else except health/login**), `GET/PUT/DELETE /api/provider-limits[/{provider}]` returning each limit with `used_sen` and `remaining_sen`. Every request/response model lists `*_sen` integers; no float money anywhere in the OpenAPI.
- **Verify:** `uv run pytest tests/test_providers_api.py`; a test walks the generated OpenAPI and fails if any property named `*amount*`, `*price*`, `*limit*` or `*sen*` has `type: number` instead of `integer`.

### Task C2 — Transactions and month summary routes
- **Files:** `backend/app/api/transactions.py`, `backend/app/api/summary.py`, `backend/tests/test_transactions_api.py`.
- **Steps:** `GET /api/transactions?start&end&type&category` (dates required or defaulted to the last 90 days; paged past 1000 via the repository), `POST`, `PATCH /{id}`, `DELETE /{id}`; `GET /api/summary/months` → `month_summary` plus `history_span`. Unknown or other-user id → 404 `transaction_not_found`.
- **Verify:** `uv run pytest tests/test_transactions_api.py` — round-trip, validation errors in the envelope, and a two-user test per route.

### Task C3 — CSV import routes
- **Files:** `backend/app/api/imports.py`, `backend/tests/test_imports_api.py`.
- **Steps:** `POST /api/import/csv` (multipart, `.csv` only, ≤ 5 MB) → preview rows with duplicate flags against `fingerprints(db, user_id)`; `POST /api/import/confirm` receives the edited rows (≤ 5,000), re-validates each (amount > 0, type, date), inserts via `bulk_create`, sets `onboarding_state` to `history_imported`, returns counts (`created`, `skipped`). No server-side preview state.
- **Verify:** `uv run pytest tests/test_imports_api.py` — upload → confirm → `GET /api/summary/months` shows the data; re-uploading the same file flags every row as a duplicate; user B's import never appears for user A.

### Task C4 — Recurring items routes
- **Files:** `backend/app/api/recurring.py`, `backend/tests/test_recurring_api.py`.
- **Steps:** `GET`, `POST`, `PATCH /{id}`, `DELETE /{id}` for manual items.
- **Verify:** `uv run pytest tests/test_recurring_api.py` with a two-user test per route.

### Task C5 — Plans and bills routes
- **Files:** `backend/app/api/plans.py`, `backend/app/api/bills.py`, `backend/tests/test_plans_api.py`.
- **Steps:**
  - `POST /api/plans/preview` — pure: provider key, item, price, fee %, instalments, purchase date, optional first payment date **or** the manual fields; applies the user's remaining limit (`split_for_limit`) and returns `financed_sen`, `upfront_sen`, the schedule and `limit_known`. The frontend never computes any of it (D-17).
  - `POST /api/plans` — the same inputs; rejects `limit_exhausted`; creates the plan, logs the checkout parts as linked expense transactions (the upfront excess, and an Atome first instalment marked paid); returns the enriched plan.
  - `GET /api/plans`, `GET /api/plans/{id}`, `PATCH /api/plans/{id}` (rename only; also updates linked descriptions whose suffix matches — port `plan_edit`), `DELETE /api/plans/{id}?keep_payments=true`, `POST /api/plans/{id}/installments/{seq}/pay`, `POST /api/plans/{id}/pay` (bulk), `GET /api/bills`.
  - Manual "Other provider" plans carry `schedule_source='manual'` and the UI note flag.
- **Verify:** `uv run pytest tests/test_plans_api.py` — worked example from the author (limit RM200 / price RM300 → RM100 at checkout, RM200 financed, both appear in the response and the ledger); Atome checkout instalment; manual provider with a typed total of RM100.01 over 3 → 33.33 / 33.33 / 33.35; delete with keep vs delete payments; a two-user test per route; limit-exhausted rejection.

### Task C6 — Regenerate the typed client
- **Files:** `frontend/lib/api/schema.d.ts`.
- **Steps:** `cd frontend && npm run gen:api`; commit the result.
- **Verify:** `npm run check:api && npx tsc --noEmit && npm run lint && npm run test && npm run build` all pass; the OpenAPI money-type test from C1 still passes.

---

## Wrap-up (do not skip)

- [ ] `refdocs/STATUS.md` — phase table, verification ledger (name each command and result; mark integration tests unrun if they are)
- [ ] `refdocs/changelog/CHANGELOG.md` — session entry, including anything `ASSUMED:` that was built on
- [ ] `refdocs/changelog/DECISIONS.md` — D-29 added (and PRD §7); ASSUMED 5 resolved or restated
- [ ] This doc updated to match what actually happened
- [ ] Reviews run: `python-reviewer` + `fastapi-reviewer` on the new Python, `security-reviewer` on the import path and every new route
- [ ] File-structure doc written (the domain layer now exists)
- [ ] Next: write `refdocs/plans/<date>-p2-synthetic-population.md` + its execution doc
