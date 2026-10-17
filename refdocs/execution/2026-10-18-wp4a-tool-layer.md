# Execution — WP4a Assistant tool layer

> Companion plan: `refdocs/plans/2026-10-18-wp4a-tool-layer.md`.

## Tasks
1. Shared functions: `api/risk.check_for`, `api/risk.confirm_for` (done, commit af32943); `api/forecast.forecast_for`, `api/provider_limits.limits_for` (WP15); budgets/insights/recommendations `*_for` (WP2–WP15).
2. Tests first: `tests/assistant/test_tools.py` (every tool), `test_policy.py` (tiers, `user_id`), `test_tool_isolation.py` (every tool as the other user).
3. `app/assistant/{context,tools,policy,executor}.py`; `POST /api/assistant/run` (guided). Verify: tests pass, `gen:api`.

## Wrap-up
CHANGELOG, STATUS; commit and push.
