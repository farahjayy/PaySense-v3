# Execution — WP15 Recommendations and alerts

> Companion plan: `refdocs/plans/2026-10-18-wp15-recommendations-alerts.md`.

## Tasks
1. Shared functions: `api/forecast.forecast_for`, `api/provider_limits.limits_for` (routes now call them).
2. Tests first: `tests/domain/test_recommendations.py` (fire / not fire per rule; figures traced), `tests/api/test_recommendations_api.py`.
3. `app/domain/recommendations.py`; `api/recommendations.py` routes. Verify: tests; `gen:api`.

## Wrap-up
CHANGELOG, STATUS, DECISIONS (ASSUMED 25); commit and push.
