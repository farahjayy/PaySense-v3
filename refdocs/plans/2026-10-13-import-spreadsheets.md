# Plan — Import: spreadsheets, and the file's own type and category

> Execution: `refdocs/execution/2026-10-13-import-spreadsheets.md`. Scope source: PRD §3 (import is P1/P7). Decision record: D-42.

## 1. Why this exists

The author imported a month of her own spending (a spreadsheet with the columns Type, Date, Item, Amount (RM), Category, saved as CSV) and found three things wrong:

1. Only `.csv` was accepted. People keep their budgets in Excel and expect an Excel file to work.
2. **The file's Type and Category columns were ignored.** Every row came in as "Spending" with a "no sign on amount, assumed expense" warning, and the category was a keyword guess on the item name (most became "Other"), although the file already said what each row was. The two income rows were guessed as spending too.
3. It was not clear what the ticks on the review screen are for.

The first two are the same defect: the importer trusts a guess over the data the person typed.

## 2. What's already covered

- The parser (`domain/csv_import.py`) already finds date, amount, debit/credit and description columns by header name, reports every unusable row with a reason and flags duplicates.
- The review screen already lets a person change each row's category and type, and untick rows. A category the dropdown does not list is already shown as an extra option, and the API accepts any category up to 60 characters.
- `openpyxl` and `defusedxml` are installed, but only in the offline `ml` dependency group, not in the API's runtime dependencies.

## 3. Scope

**In**
- **Type and Category columns.** When the file has them, their values are used; the keyword guess is only the fallback for an empty or missing cell. Type words are matched case-insensitively (expense, income, savings, plus debit/credit, spending, etc.); a value that is not recognised falls back to the old rules and says so on the row. Category text is kept as written (trimmed), matched case-insensitively to the app's list when it is one of them, kept verbatim when it is the person's own ("Hangout", "Drink / Dessert"). The reserved name `BNPL` is not taken from a file (D-29: assigned by the app only).
- **Excel files.** `.xlsx` and `.xlsm` read on the server with `openpyxl` (read-only, cached values, so formulas arrive as the numbers Excel last calculated). Real date cells, number cells, a title or notes above the header row, several sheets (every sheet that has a table is read; every sheet that is skipped is named in a note), hidden sheets skipped with a note.
- **Other spreadsheet layouts and text files.** Separate "Income" and "Expense" columns; tab-separated and `.txt` exports; Excel's Windows-1252 and UTF-16 "Unicode text" encodings; the header row anywhere in the first 30 rows.
- **Review screen.** A line saying that only ticked rows are saved, the file's own categories offered in each row's dropdown, a note banner for skipped sheets, and wording that says "statement or spreadsheet".
- The Transactions screen's category filter lists the categories actually in the ledger, so an imported "Hangout" can be filtered.

**Out, with reasons**
- **`.xls` (Excel 97-2003) and `.ods`.** Reading `.xls` needs `xlrd`, and there is no way to write a test file in that format with the installed tools, so it would ship untested. The upload says exactly how to save it as `.xlsx`. Easy to add later if a tester needs it.
- **Mapping the file's categories into the app's twelve.** That would be a guess, which is the defect being fixed.
- **Letting the person choose the columns on screen.** The header-name matching covers the layouts seen; a mapping screen is a feature of its own.
- **Renaming the route `/api/import/csv`.** It would touch every client and test for no behaviour change; the name is recorded as known debt.
- Password-protected workbooks (they are not zip files; the message says to remove the password), macros (never executed: `openpyxl` does not run them), images, charts.
- **Found by the security review, deliberately left alone:** (1) the category `BNPL` is refused from an imported file but can still be set through `/import/confirm` and the transactions routes, which accept any text up to 60 characters; it only affects the person's own forecast. (2) Text starting with `=`, `+`, `-` or `@` is stored as written; nothing exports user rows today (no download route, no `dangerouslySetInnerHTML`), so it is inert, but any future transactions export or P9 results export must prefix such cells with `'`. (3) Parsing in a resource-limited child process: the caps and the two-at-a-time gate were chosen instead.

## 4. Approach

- One table-reading core. CSV text and each Excel sheet are turned into a list of rows of strings, then the same code finds the header, locates the columns and reads the rows. Excel-specific work is only the conversion of cells to text (dates to ISO, floats rounded away from binary noise, never multiplied: money stays integer sen, D-16).
- A new module `domain/upload.py` owns "bytes and a file name to a preview" (text decoding, workbook reading, safety limits). `csv_import.py` stays pure.
- The preview response gains `notes: list[str]` (skipped sheets). `category_guess` keeps its name (renaming the field would ripple through the client for no behaviour change) but now carries the file's category when there is one.
- Workbook safety, because a `.xlsx` is a zip file from a stranger: refuse more than 20 MB uncompressed or more than 500 parts before parsing (zip bombs), parse with `defusedxml` active (XML entity attacks), read-only streaming with a hard cap on rows scanned, at most 64 columns, at most 20 sheets, and any parser failure becomes a coded 422, never a 500.

## 5. Risks & unknowns

| Risk | Confidence | Mitigation |
|---|---|---|
| `openpyxl` read-only mode pads or trims rows differently from what I expect | Medium: I have not read its row semantics for ragged rows | Tests with ragged rows, a cell far below the data, and a stored-text amount |
| Formulas have no cached value if the file was written by a script (not by Excel) | High that this happens | Such cells are blank, so the row is reported as "missing amount"; the message is not hidden |
| A header word ("type", "category", "income", "expense") matches an unrelated column | Medium | New debit/credit words match whole headers only; type and category headers are matched exactly first |
| A person's own category named like a reserved one ("Transfer") changes forecasting | Low | It is a real choice and is already in the dropdown; only `BNPL` is refused |
| Excel's date cells in a different locale arrive as real dates, text dates are dd/mm/yyyy (as now) | High | Real dates are exact; text keeps the existing day-first rule and the review screen shows the parsed date |

## 6. Definition of done

- Importing a file with Type and Category columns shows the file's own type and category on every row, with no "assumed expense" warning, in the browser (the same screen as the screenshot).
- An `.xlsx` of the same table gives the same preview as its CSV.
- Every new branch has a test that failed first; backend and frontend suites, lint, type check and the API drift check pass; the commands and results are in the changelog.
- A security review of the workbook path has been run and its findings fixed or recorded.
- Docs updated: D-42, PRD §7, changelog, STATUS.
