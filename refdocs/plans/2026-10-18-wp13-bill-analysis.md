# Plan — WP13 Bill analysis

> Execution: `refdocs/execution/2026-10-18-wp13-bill-analysis.md`. Scope: work-packages.md WP13 (Topic A: bill analysis).

## 1. Why this exists
"What do I owe this month?" is the second question a student with several BNPL plans asks. Bills and instalments from different providers land in the same week more often than people notice; a bill that quietly went up is easy to miss.

## 2. What's already covered
Confirmed recurring items (income and bills, with cadence and anchor), `engines/forecasting/flows.occurrences` (when an item falls), plan schedules with paid flags, `normalise_merchant` (how a ledger row is matched to an item), monthly bills (`domain/bills.py`).

## 3. Scope
**In:** `domain/bill_analysis.py`: recurring-bills summary (count, monthly total from each cadence, share of confirmed recurring income); bills whose amount went up (latest vs previous logged occurrence of the same confirmed item); the next 30 days' due list (bills and unpaid instalments, overdue instalments flagged); collisions (two or more items due within the same 7-day window, with the total). `GET /api/insights/bills`; the tool `get_bill_analysis` (WP4a).
**Out:** predicting bill amounts (Engine 1's job); bills not confirmed as recurring items (detected suggestions are not bills until the person confirms them).

## 4. Approach
- Monthly cost from cadence: monthly ×1, weekly ×52/12, biweekly ×26/12, semester ÷6, custom ×(365.25/12)/interval; rounded to sen.
- A ledger row is an occurrence of an item when it carries the item's id, or its type and normalised merchant text equal the item's (the same rule `unlogged_occurrences_net` uses).
- Collisions: due items sorted by date, grouped greedily into windows of 7 days starting at the first item not yet grouped; a window with two or more items is a collision. Overdue instalments are listed (flagged) but not part of collisions.
- One shared function (`bills_for`) behind the route and the tool.

## 5. Risks & unknowns
| Risk | Confidence | Mitigation |
|---|---|---|
| A bill logged under a slightly different description is missed as an increase | Medium | Same matching rule as Engine 1; stated in the response field description |
| Greedy windows can split a dense run differently from a sliding window | Low | Every item still appears in exactly one window; tests pin the behaviour |

## 6. Definition of done
Tests for increases, collisions across providers, no recurring items, a plan paid early; two-user and unauthenticated tests.
