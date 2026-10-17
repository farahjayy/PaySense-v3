# Execution — WP-API Contract first

> Companion plan: `refdocs/plans/2026-10-18-wp-api-contract.md`.

## Tasks
1. **Contract test first** — `backend/tests/api/test_contract_wp_api.py`: every new route present, 401 without a session, typed card/action unions, plain-text history, no `user_id`. Verify: failed before the routes existed.
2. **Models and stubs** — `app/api/budgets.py`, `insights.py`, `recommendations.py`, `assistant.py`; routers registered in `app/main.py`; 501 mapped to `not_implemented`. Verify: `uv run pytest tests/api tests/test_openapi.py tests/test_export_openapi.py -q` → 400 passed (the money-contract test failed once on `share_of_income`; renamed `bills_share`).
3. **Types** — `cd frontend && npm run gen:api && npx tsc --noEmit`. Verify: clean.

## Wrap-up
CHANGELOG, STATUS; commit and push.
