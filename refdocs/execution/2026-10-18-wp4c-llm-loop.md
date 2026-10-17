# Execution — WP4c LLM loop and guardrails

> Companion plan: `refdocs/plans/2026-10-18-wp4c-llm-loop.md`.

## Tasks
1. Tests first: `tests/assistant/test_llm_adapters.py` (Gemini and Anthropic request/response mapping over `httpx.MockTransport`, schema flattening, errors → `LLMError`), `test_number_check.py`, `test_agent.py` (scripted conversations, caps, fallback, out of scope, budgets, opening, status, key never leaked).
2. `app/assistant/llm.py`, `numbers.py`, `prompt.py`, `agent.py`; routes; `create_app(..., llm=)` for tests. Verify: tests pass; `gen:api`.
3. One live smoke call through `GeminiLLM` with no user data. Verify: a tool call comes back.

## Wrap-up
CHANGELOG, STATUS, DECISIONS (ASSUMED 28), questions; commit and push.
