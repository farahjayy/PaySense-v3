# Execution — WP13 Bill analysis

> Companion plan: `refdocs/plans/2026-10-18-wp13-bill-analysis.md`.

## Tasks
1. Tests first: `tests/domain/test_bill_analysis.py`, `tests/api/test_insights_bills_api.py`. Verify: fail.
2. `app/domain/bill_analysis.py`; `DueItemOut.overdue`; `api/insights.bills_for` + route. Verify: tests pass; `gen:api`.

## Wrap-up
CHANGELOG, STATUS; commit and push.
