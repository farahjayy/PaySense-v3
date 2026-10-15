# Execution — P7b Ledger polish, categories, and plainer wording

> Plan: `refdocs/plans/2026-10-15-p7b-ledger-polish.md`. Tasks run top to bottom. Each carries its own **Verify**; a task is not done until its Verify passes.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4).

## Before starting

- Read `CLAUDE.md`, `refdocs/STATUS.md`, ADR D-13, D-27, D-28, D-29, D-42.
- `progress_material/` holds the author's real bank statements and is gitignored (added 2026-10-15); nothing from it is copied into the repo, tests or docs. Tests build their own synthetic workbooks.
- Backend commands run from `backend/` with `.venv/Scripts/python.exe -m ...`; frontend from `frontend/`.

---

### Task L1 — Excel column guard (tests first)
- **Files:** `backend/app/domain/upload.py`, `backend/tests/domain/` (the upload tests).
- **Found:** `_scan_cells` counts `<c>` per `<row>` in every XML part. `xl/calcChain.xml` lists one `<c>` per formula cell with no `<row>`, so a workbook with more than 64 formulas is refused as "more than 64 columns". Reproduced on the author's workbook (13 sheets, at most 10 cells in any row, 75 entries in `calcChain.xml`).
- **Steps:** count a `<c>` only while inside a `<row>`; keep the per-sheet total cap for every part. Test: a valid workbook with an injected `calcChain.xml` of 80 entries reads; a genuinely wide row (70 cells) is still refused.
- **Verify:** the two tests; then the real importer on `progress_material/farah_spending_history.xlsx` reports rows read.

### Task L2 — Merchant text ignores month names (tests first)
- **Files:** `backend/app/domain/merchants.py`, `backend/tests/domain/test_merchants.py`, `backend/tests/engines/` (recurring detection).
- **Steps:** drop whole-word month names and three-letter forms (`jan` … `dec`, `sept`) after lower-casing. Tests: "July PESP Allowance" and "June PESP Allowance" normalise equal; "Maybank" and "Mayflower Cafe" are unchanged; detection suggests one item from "Rent july/august/september" on the 25th, 28th, 30th and 1st.
- **Verify:** `pytest tests/domain tests/engines -q`, then the whole suite (synthetic profiles and the serving checks must not move).

### Task L3 — Category breakdown (tests first)
- **Files:** `backend/app/domain/breakdown.py`, `backend/app/api/summary.py`, `backend/tests/domain/test_breakdown.py`, `backend/tests/api/test_summary_categories_api.py`.
- **Steps:** `category_breakdown(rows)` groups spend rows by category using `flows.classify`; transfers are ignored, refunds are netted against total spend (not a category), savings are reported separately; `share` is the category's part of gross category spend. Route `GET /api/summary/categories?month=YYYY-MM`, newest data only for that month, user-scoped; month outside `YYYY-MM` is a 422.
- **Verify:** the panel total equals `month_summary(...).spend_sen` for the same rows; a two-user isolation test; an unauthenticated 401; the money-fields-are-sen OpenAPI test still passes.

### Task L4 — Categories (tests first)
- **Files:** `backend/migrations/0002_user_categories.sql`, `backend/migrations/README.md`, `backend/app/domain/categories.py`, `backend/app/db/base.py` (`update_where`), `backend/app/db/categories.py`, `backend/app/db/transactions.py` (`recategorise`, `category_counts`), `backend/app/api/categories.py`, `backend/app/main.py`, `backend/tests/fakes.py`, tests for each.
- **Steps:** table `user_categories (id, user_id, name, created_at)`, unique on `(user_id, lower(name))`, RLS on with no policies, grants revoked. `GET /api/categories` returns built-in (locked) then the author's own (table plus any other category on a transaction) with a transaction count. `POST` adds; `PATCH` renames and rewrites the transactions; `DELETE` removes and moves transactions to `move_to` (required when any use it). Case-insensitive duplicates are refused (409); built-in names are locked (409); the destination of a move must exist.
- **Verify:** repository and API tests including two-user isolation for every function; a rename moves exactly the caller's rows; deleting a used category without `move_to` is refused.

### Task L5 — Regenerate the API contract
- **Steps:** `cd frontend && npm run gen:api && npm run check:api`.
- **Verify:** `check:api` exits 0 and `schema.d.ts` contains the new paths.

### Task L6 — Dashboard wording, layout and checklist (tests first)
- **Files:** `frontend/components/forecast/MarginFan.tsx`, `RecentMonths.tsx`, `frontend/components/screens/DashboardScreen.tsx`, `frontend/components/dashboard/GettingStarted.tsx`, tests.
- **Steps:** caption and table headings per the plan; a note under the table; Recent months with no minimum width and short month labels; the row split about 2:3 and a wider page; the checklist reads transactions, recurring items, limits, plans and the forecast and hides when every step is done.
- **Verify:** unit tests for each; axe test still clean.

### Task L7 — BNPL result card wording
- **Files:** `frontend/components/plans/PlanPreviewPanel.tsx`, its test.
- **Steps:** per the plan; every figure still comes from the server's preview. The fee is `total_payable_sen - financed_sen`, shown only when `financed_sen > 0`.
- **Verify:** the author's case (price 3,500, 6 instalments, 3%, RM 2,300 left) renders RM 1,550.85 / RM 1,949.15 / RM 350.85 / RM 2,300.00 / RM 3,850.85.

### Task L8 — Transactions page
- **Files:** `frontend/components/screens/TransactionsScreen.tsx`, `frontend/components/transactions/{CategorySpending,TypeButtons,MonthStepper,BnplBox}.tsx`, `frontend/lib/queries` hooks, tests.
- **Steps:** month stepper (defaults to the latest month with data), Type buttons, category dropdown fed by the categories hook with the fallback, search over description and category, the category panel (click filters, click again clears), the BNPL side box from the plans list.
- **Verify:** unit tests; the existing screen tests updated, not deleted.

### Task L9 — Categories page, template, import note, nav
- **Files:** `frontend/app/(app)/categories/page.tsx`, `frontend/components/screens/CategoriesScreen.tsx`, `frontend/public/paysense-import-template.csv`, `frontend/lib/nav.ts`/`AppShell.tsx`, `ImportScreen.tsx`, tests.
- **Verify:** add / rename / delete flows; locked rows have no actions; the template's header is exactly `type,date,item,amount,category`; backend test imports an identical template through the real importer.

### Task L10 — Whole-project verification and reviews
- **Commands:** `cd backend && .venv/Scripts/python.exe -m ruff check . && ruff format --check . && .venv/Scripts/python.exe -m pytest -q`; `cd frontend && npx tsc --noEmit && npm run lint && npx vitest run && npm run build && npx playwright test`.
- **Reviews:** security (new user-scoped routes, a migration), python/fastapi, react.
- **Verify:** all green; results written to the changelog and STATUS ledger.

## Wrap-up

- [ ] CHANGELOG entry (reported, diagnosed, changed, decided, deviations, verified, noted-not-changed)
- [ ] STATUS: P7 row, verification ledger, Known gaps (migration 0002 not yet applied to the real project)
- [ ] ADR D-43, D-44, D-45 in `DECISIONS.md`; one-liners in PRD §7
- [ ] `migrations/README.md` lists 0002
