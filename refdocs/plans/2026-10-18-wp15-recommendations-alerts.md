# Plan — WP15 Ranked recommendations and proactive alerts

> Execution: `refdocs/execution/2026-10-18-wp15-recommendations-alerts.md`. Scope: work-packages.md WP15 (Topic A: recommendations, proactive alerts).

## 1. Why this exists
A finance assistant should say what needs attention before it is asked, and rank what to do next. Every suggestion has to be checkable: it shows the figures it came from, and those figures come from an engine or the person's own data.

## 2. What's already covered
Engine 1's forecast (`forecast_for`), budget status (WP2), bill analysis (WP13), spending insights (WP14), provider limits (`limits_for`).

## 3. Scope
**In:** `domain/recommendations.py` — a fixed, ordered rule set over those outputs only; each recommendation carries its source figures, a priority, a severity and an action (a link, or a pre-filled `set_budget` proposal that still needs confirmation, D-48). `alerts` = the subset that needs attention now. `GET /api/recommendations`, `GET /api/alerts`; tools `get_recommendations`, `get_alerts`.
**Out:** any new model or score; free-text advice; anything that writes.

## 4. Approach — the rules, in priority order
| # | Rule | Fires when | Severity | Alert |
|---|---|---|---|---|
| 1 | `forecast_shortfall` | forecast ok and P(shortfall) ≥ 0.10 (the Safe edge) | high if ≥ 0.30 (At Risk) else medium | when ≥ 0.30 (`ASSUMED` 25: "above the Caution edge" read as At Risk) |
| 2 | `budget_over` | a budget at ≥ 100% this month | high | yes |
| 3 | `bill_collision` | a collision in the next 30 days | high if it starts within 7 days, else medium | within 7 days |
| 4 | `budget_near` | a budget at ≥ 80%, or projected to pass 100% by month end | medium | no |
| 5 | `plan_near_limit` | a provider limit ≥ 80% used | medium | no |
| 6 | `bill_increase` | a confirmed bill went up | medium | no |
| 7 | `spending_up` | last complete month: the top category up ≥ 20% and ≥ RM50 | low | no — proposes a budget at the earlier month's level if none exists |
| 8 | `forecast_locked` | the forecast is locked | low | no |
| 9 | `no_budgets` | no budgets and some spending this month | low | no |
Each sentence is built from its `sources`; a test extracts every number from the title and detail and asserts it appears in the formatted sources.

## 5. Risks & unknowns
| Risk | Confidence | Mitigation |
|---|---|---|
| Too many recommendations on a stretched persona | Medium | At most three per rule; ordered; alerts are a short subset |
| Running the forecast on every call is CPU-heavy | Medium | Same per-user limit as the forecast route |

## 6. Definition of done
Every rule has a test that fires and one that does not; every figure in a recommendation traces to a source (asserted); routes have two-user and unauthenticated tests.
