# Plan — WP4c LLM loop and guardrails (D-47, D-53)

> Execution: `refdocs/execution/2026-10-18-wp4c-llm-loop.md`. Scope: work-packages.md WP4c, section 3.3.

## 1. Why this exists
The competition theme is an AI agent that completes real tasks. The tool layer (WP4a) and pending actions (WP4b) make that safe; this package adds the model that turns a sentence into tool calls and writes a short narration — without ever being trusted with a number or a write.

## 2. What's already covered
Tools, tiers, executor, guided mode, proposals and confirm, the audit log, assistant settings.

## 3. Scope
**In:** `assistant/llm.py` — one provider-neutral interface (messages, tool specs, tool calls, token usage) with `GeminiLLM` (Gemini API `generateContent` with function calling; free tier; default model `gemini-3.8-flash`, the model the API itself names as current for new keys), `AnthropicLLM` (Messages API with tool use; default `claude-sonnet-5-5`), `FakeLLM` (scripted, for every test; never touches the network). `assistant/agent.py` — the loop (max tool calls per turn, output-token cap, an overall deadline, history capped to the last N plain-text turns), the system prompt, the untrusted-data rule (pasted text and tool-result text fields are labelled data), out-of-scope refusal, the **number check** with a template fallback, guided-mode fallback when the provider fails, per-user and global daily token budgets, and an audit row for every message, tool call, reply, refusal and fallback. Routes: `POST /assistant/chat`, `GET /assistant/status`, `GET /assistant/opening` (alerts, no model call).
**Out:** streaming; the live evaluation (WP6); paste parsing (WP4d).

## 4. Approach
- **Schemas:** the registry's Pydantic schemas are flattened once per provider (`$ref` inlined, `anyOf [X, null]` → X, titles dropped) because Gemini's function declarations take an OpenAPI subset.
- **Gemini specifics:** a function-call part carries an `id` and a `thoughtSignature` that must be sent back unchanged; the adapter keeps the model's raw parts on the assistant message and echoes them.
- **Number check:** every figure in the narration (amounts, percentages, counts, dates) must appear among the figures of this turn's tool results (RM forms of every `*_sen`, percentages of every probability or share, the parts of every date), the server's own step summaries, or the user's current message; small whole numbers up to 12 are allowed (`ASSUMED` 28: counts like "3 instalments"). History is never a source (it comes from the client). On failure the narration is replaced by a template built from the step summaries, `narration_replaced: true`, and a `fallback` audit row.
- **Out of scope:** the system prompt tells the model to answer exactly `OUT_OF_SCOPE`; the agent replaces it with a fixed refusal (`refused: true`).
- **Failures:** any provider error, timeout or malformed answer → guided-mode reply with whatever cards were already produced, `mode: guided`, a `fallback` audit row. No key, `LLM_PROVIDER=none` or `ASSISTANT_ENABLED=false` → guided mode from the start.
- **Budgets:** before a model call, today's tokens (per user and global, Malaysian day, from the audit log) are checked against `ASSISTANT_USER_DAILY_TOKENS` / `ASSISTANT_GLOBAL_DAILY_TOKENS`; over → 429 `assistant_daily_budget` (guided mode still works). Chat is also rate limited per user.
- **Keys:** optional `SecretStr`; sent only in request headers; never logged, never in a response, never in the audit log (a test scans responses and log records).

## 5. Risks & unknowns
| Risk | Confidence | Mitigation |
|---|---|---|
| Free-tier latency or quota errors during a demo | High | Guided fallback; live evaluation reports latency honestly |
| The number check replaces good narration that rounds differently | Medium | Accept the common RM/percentage forms; report the fallback rate in WP6 |
| Anthropic adapter untested live (no credit) | Certain | Tested with a mocked transport; questions.md |

## 6. Definition of done
With the fake LLM, scripted conversations produce the expected tool sequences; the number check rejects an invented figure; no key → guided mode; the key never appears in logs or responses.
