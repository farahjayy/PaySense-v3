# Execution — Import: spreadsheets, and the file's own type and category

> Plan: `refdocs/plans/2026-10-13-import-spreadsheets.md`. Tasks run top to bottom. Each task carries its own **Verify** step; a task is not done until its Verify actually passes.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4).

## Before starting

- Read `CLAUDE.md`, `refdocs/STATUS.md`, ADR D-16 (integer sen), D-29 (import is stateless; reserved categories), D-14 (public repo).
- **No real data in tests.** The author's own file is the motivating example only; the fixtures are invented rows of the same shape.

---

### Task I1 — Table core: type and category columns, header scan, delimiters (tests first)
- **Files:** `backend/app/domain/csv_import.py`, `backend/app/domain/categorize.py`, `backend/tests/domain/test_csv_import.py`.
- **Steps:** (1) tests: type column wins over the amount's sign and removes the "no sign" note; unknown type word falls back and says so; blank type falls back to the file-level rules; category kept verbatim and trimmed; case-insensitive match to the app's list; empty category falls back to the keyword guess; `BNPL` refused with a note; over-long category cut to 60; separate Income / Expense columns; header after title rows; semicolon, tab; a delimiter that only looks right in the title row. (2) implement; the existing tests must still pass unchanged.
- **Verify:** `cd backend && uv run pytest tests/domain/test_csv_import.py -q`.

### Task I2 — Upload module and Excel reading (tests first)
- **Files:** `backend/app/domain/upload.py`, `backend/tests/domain/test_upload.py`, `backend/pyproject.toml` (`openpyxl` and `defusedxml` move to runtime dependencies), `backend/uv.lock`.
- **Steps:** tests with workbooks built in memory: dates, floats with binary noise, text amounts, a title row, two sheets, a hidden sheet, a sheet without a table, ragged rows, a stray cell far below the data, more than 5,000 rows, more than 64 columns, not a zip, a zip bomb (a 30 MB entry that compresses to a few KB), a workbook with an XML entity bomb, Windows-1252 and UTF-16 text. Then implement `decode_text`, `read_workbook`, `file_kind`, `parse_upload`.
- **Verify:** `uv run pytest tests/domain/test_upload.py -q`; the bomb tests finish in well under a second and do not grow memory.

### Task I3 — API
- **Files:** `backend/app/api/imports.py`, `backend/tests/api/test_imports_api.py`.
- **Steps:** extension check through `file_kind` (`.xls` gets its own message); `parse_upload`; `notes` in the response. Tests: an `.xlsx` upload, the same table as CSV and as xlsx gives equal rows, `.xls` message, a corrupt `.xlsx` is a 422 with a code, notes appear, a custom category survives preview then confirm, two-user isolation unchanged.
- **Verify:** `uv run pytest tests/api/test_imports_api.py -q`, then the whole backend suite and `uv run ruff check . && uv run ruff format --check .`.

### Task I4 — Typed client
- **Steps:** `cd frontend && npm run gen:api`; commit the regenerated `lib/api/schema.d.ts`.
- **Verify:** `npm run check:api` exits 0.

### Task I5 — Frontend (tests first)
- **Files:** `frontend/lib/import.ts`, `components/import/{DropZone,ReviewList}.tsx`, `components/screens/{ImportScreen,TransactionsScreen}.tsx`, `tests/unit/{import.test.ts,ImportScreen.test.tsx}`, `tests/e2e/journey.spec.ts` (the label).
- **Steps:** accepted extensions and the message; the hint that only ticked rows are saved; the file's categories offered in each row's dropdown (and kept when another row is changed); the notes banner; the Transactions category filter lists categories in the ledger; the file input's label no longer says CSV.
- **Verify:** `cd frontend && npm run lint && npx tsc --noEmit && npm run test && npm run build`.

### Task I6 — Reviews, docs, commit
- **Steps:** python-reviewer and security-reviewer on the new modules (a workbook is untrusted input); fix findings with a failing test first. D-42 and its PRD §7 line; changelog entry; STATUS; both README indexes. One conventional commit per verified group; never push; never stage `progress_material/`.
- **Verify:** full backend and frontend suites green; the real file shape imported through `parse_upload` shows Type and Category as written.
