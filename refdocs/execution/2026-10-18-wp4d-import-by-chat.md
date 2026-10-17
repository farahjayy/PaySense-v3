# Execution — WP4d Import by chat

> Companion plan: `refdocs/plans/2026-10-18-wp4d-import-by-chat.md`.

## Tasks
1. Tests first: `tests/assistant/test_paste.py` (grounding of amounts and dates, descriptions, caps, duplicates, injection, deterministic fallback, paste → preview → confirm through the API).
2. `app/assistant/paste.py`; `ToolContext.pasted_text`; the tool; `agent` passes the turn's paste; guided `/assistant/run` accepts `pasted_text`. Verify: tests; `gen:api`.

## Wrap-up
CHANGELOG, STATUS, DECISIONS (ASSUMED 30); commit and push.
