# Plan — WP14 Spending insights

> Execution: `refdocs/execution/2026-10-18-wp14-spending-insights.md`. Scope: work-packages.md WP14 (Topic A: spending insights).

## 1. Why this exists
"How am I doing?" needs an answer a student can check: which categories moved since last month, anything out of the ordinary, and how much of the income was kept.

## 2. What's already covered
The month summary and category breakdown (`flows.month_summary`, `breakdown.category_breakdown`, D-45) — the only definitions of income, spending, refunds and savings used here.

## 3. Scope
**In:** `domain/insights.py`: per-category change against the previous calendar month (sen and %; new / gone / up / down / same), the three biggest movers, unusual transactions (above the person's own robust threshold for that category), the savings rate, a headline chosen by a fixed rule; `GET /api/insights/spending?month=`; the tool `get_spending_insights`.
**Out:** any forecast (Engine 1's job); judging plan payments as unusual (they are scheduled).

## 4. Approach
- Totals come from `category_breakdown`, so they equal the month summary.
- **Unusual:** for each category, the spending rows of up to 24 months **before** the month are its history; a row in the month is unusual when it is above `median + k × 1.4826 × MAD` of that history, with **k = 3** (`ASSUMED` 23: three robust standard deviations). Needs at least 5 earlier rows; a category whose history has no spread (MAD 0) is not judged. BNPL plan payments are never judged. Both cases are said in `unusual_note`.
- **Savings rate** = what was left over (income − spending) ÷ income, `None` with no income. Money logged as Savings (D-45, "set aside") is reported beside it, with its own share of income, never added (`ASSUMED` 24).
- **Headline** — the first rule that applies, in this order: nothing logged; spent more than came in; a category up by at least 20% and RM50; kept at least 20% of income; a category down; otherwise what was spent. The rule key is returned, and every figure in the sentence comes from the response.

## 5. Risks & unknowns
| Risk | Confidence | Mitigation |
|---|---|---|
| k = 3 flags too little or too much | Medium | `ASSUMED`; the threshold and median are returned with each flagged row |
| "Savings rate" read as money set aside | Medium | Both are returned and named; `ASSUMED` 24 asks the author |

## 6. Definition of done
Tests for a first month (no comparison), a category that appears or vanishes, refunds, the BNPL row, too little history for "unusual"; totals equal the month summary; two-user and unauthenticated tests.
