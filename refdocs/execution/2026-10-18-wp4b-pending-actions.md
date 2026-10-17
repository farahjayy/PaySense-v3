# Execution — WP4b Pending actions, confirm, audit log

> Companion plan: `refdocs/plans/2026-10-18-wp4b-pending-actions.md`.

## Tasks
1. Migration 0004: `assistant_actions`, `assistant_events`. Fakes. `check_rls.py`.
2. Tests first: `tests/assistant/test_actions.py` (propose validation and reuse, confirm per type, replay, double confirm, expiry, wrong user, tampered payload, failed write, decline, audit rows), `tests/test_assistant_repos.py`.
3. `db/assistant_actions.py`, `db/assistant_events.py`, `assistant/actions.py` (propose, confirm, decline, `action_out`), the `propose_action` tool, routes. Verify: tests; `gen:api`.

## Wrap-up
CHANGELOG, STATUS, questions (0004 now also holds the assistant tables); commit and push.
