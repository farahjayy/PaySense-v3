# Plan — P7b Ledger polish, categories, and plainer wording

> Execution: `refdocs/execution/2026-10-15-p7b-ledger-polish.md`. Scope source: the author's walk-through of the running app on 2026-10-15 (screenshots and questions), PRD §4 (Ledger, Import, Recurring items, Dashboard), ADR D-13, D-27, D-28, D-42.

## 1. Why this exists

The author went through every screen with her own spending history and found things that make the app hard to read or that quietly fail:

- Nothing tells a new student what to do first or why (recurring items, BNPL limits).
- "Your running margin" is hard to read; its table columns do not add up and nothing says why.
- Recent months is cut off and needs a sideways scroll.
- The BNPL result card says "Pay at checkout / Financed / Total you will repay", which does not say who pays whom, or what the fee is.
- The Transactions page has no spending-by-category view (v1 had one), no way to manage categories, and BNPL instalment rows look like any other row.
- Her own Excel workbook is refused with "more than 64 columns" although no row is that wide.
- "July PESP Allowance", "Rent july" and "utilities july" are treated as different recurring items, so a monthly item with the month in its text is never detected and never matched.

## 2. What's already covered

- Import of CSV and Excel with a file's own Type and Category columns (D-42); the review step already lets each row's category be changed.
- Recurring detection, matching within seven days and the "unmatched" banner (P4).
- The server's split between what a provider finances and what is paid at checkout (D-28); only the wording is changing.
- Transfer / Refund / BNPL handling in the cash-flow classification (`domain/flows.py`, D-27, D-29).
- Responsive shell with a bottom bar on phones (P7). Phone-width polish is **out of this plan** (website first).

## 3. Scope

**In**
1. **Wording and layout.** Running-margin caption and table headings with a note that the columns are typical values and do not add up; Recent months fits its card with no sideways scroll and gets the wider share of the row; the dashboard uses a wider page; the BNPL result card names who pays what, the fee, and the total cost.
2. **Getting started** checklist on the dashboard (log history, confirm recurring items, record BNPL limits, see the forecast, run a risk check) and a "why" line on the Recurring and BNPL limits sections.
3. **Merchant text ignores month names** so "Rent july" and "Rent august" are one item; existing items keep working because every comparison re-normalises stored text.
4. **Excel guard fix.** The per-row cell count applies to worksheet rows only, never to other parts of the workbook.
5. **Spending by category** on Transactions: `GET /api/summary/categories?month=`, a panel beside the list, clicking a category filters the list. Month stepper, Type as buttons, a search box.
6. **BNPL rows** show a side box naming the plan and the instalment, instead of a bare link.
7. **Categories page:** built-in categories locked, the author's own categories added, renamed and deleted (deleting moves their transactions); the lists in the transaction form and the filters come from it. Download of an import template (`type,date,item,amount,category`) from the Categories and Import pages.
8. **Import page note:** CSV and Excel only, with what to do about a PDF statement (no tool named).

**Out, with reasons**
- **PDF parsing.** Supervisor decision (D-13); stays a stated limitation.
- **Learn-from-corrections category rules.** Recorded as future work; the review step already lets her fix a row.
- **Changing how savings or transfers enter the forecast.** D-27 defines them once for the summary and the weekly series; the panel shows savings beside spending instead of redefining either.
- **Phone-width fixes and an installable app.** Website first, at the author's request.
- **Excel template with drop-downs.** A CSV template first.

## 4. Approach

- Backend: `domain/breakdown.py` (pure category totals using `flows.classify`), `domain/categories.py` (built-in list, validation), `db/categories.py` and migration `0002_user_categories.sql`, routes `api/categories.py` and `GET /api/summary/categories`. Every repository function takes `user_id` first and gets an isolation test.
- Category names travel in query strings and bodies, never in the path (a name such as "Drink/Dessert" contains a slash).
- Built-in categories (the twelve the importer guesses from, plus `BNPL`) cannot be renamed or deleted; the engines key off `Refund`, `Transfer` and `BNPL`. Any other category a transaction carries (typed in her own file) is "yours" and manageable even if it was never added by hand.
- Frontend: new components under `components/transactions/` and `components/categories/`; one hook per endpoint in `lib/api/queries.ts`; types regenerated with `npm run gen:api`.
- The forms fall back to the built-in list plus categories already on transactions if the categories call fails, so a missing migration cannot break "Add transaction".

## 5. Risks & unknowns

| Risk | Confidence | Mitigation |
|---|---|---|
| Ignoring month names changes grouping for existing ledgers and for synthetic profiles | Medium that nothing shifts; full suite plus the P4/P5 serving checks will say | Run the whole backend suite; stored `match_text` is re-normalised on every comparison; a month word only drops as a whole word |
| Migration 0002 must be applied to the real Supabase project by the author | Certain | Page degrades (fallback list); `migrations/README.md` and STATUS say it is pending; `check_rls.py` run after |
| Her real workbook fails for a second, unseen reason after the guard fix | Medium | Re-run the real importer on her file and report rows read, not "passed" |
| The category panel and the dashboard disagree about "spent" | Low | Both come from `domain/flows.classify`; a test compares the panel's total with `month_summary` |
| Renaming a category rewrites many rows | Low | One scoped bulk update per rename; the response says how many rows moved |

## 6. Definition of done

- Her `farah_spending_history.xlsx` previews through the real importer with rows read and none refused by the column guard.
- A ledger with "Rent july", "Rent august", "Rent september" suggests one monthly item.
- The Transactions page shows a spending-by-category panel for the chosen month whose total equals the month summary's spend; clicking a row filters the list.
- A BNPL instalment row shows a box naming its plan and "n of m".
- The Categories page adds, renames and deletes her own categories; built-in ones show as locked; renaming updates every transaction that used the name.
- The running-margin table, Recent months and the BNPL result card read as described in §3.
- Backend and frontend suites, lint, types, build and the Playwright journeys pass, and every command and result is in the changelog.
