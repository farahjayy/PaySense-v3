# Execution — The Second-Opinion Check

> Companion plan: `refdocs/plans/2026-10-18-second-opinion-check.md`.

## Tasks
1. `app/domain/second_opinion.py` (pure: stacked dues by month and provider, exposure, the RM1,500 line, the added probability) + tests.
2. `app/engines/risk/schedule.py` (options over dates × counts, judged by simulation; the qualifying rule) + tests with a fake evaluator.
3. API: `second_opinion` on `RiskCheckOut`; `POST /api/risk/schedule`; tests incl. isolation and rate limit. `npm run gen:api`.
4. Assistant: the block in `check_purchase_risk`'s data; Tier 1 `find_safer_timing`; policy and isolation tests.
5. Frontend: the block on the risk result (risk screen and assistant card), the schedule options with "Use this"; tests, axe, Playwright.
6. Live check on the personas; docs.
