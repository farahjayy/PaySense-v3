# Execution — WP6 Assistant tests and evaluation

> Companion plan: `refdocs/plans/2026-10-18-wp6-assistant-evaluation.md`.

## Tasks
1. `tests/assistant/test_scenarios.py`, `tests/assistant/test_security_suite.py`. Verify: pass.
2. `backend/scripts/assistant_eval.py` + `tests/test_assistant_eval.py` (with the fake LLM). Verify: pass.
3. Live run: `cd backend && uv run python scripts/assistant_eval.py --runs 3`. Verify: `reports/assistant/README.md` written from the run.

## Wrap-up
CHANGELOG, STATUS; commit and push.
