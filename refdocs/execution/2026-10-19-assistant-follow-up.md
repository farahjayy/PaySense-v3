# Execution — The assistant's follow-up turns

> Companion plan: `refdocs/plans/2026-10-19-assistant-follow-up.md` (the diagnosis and the acceptance rule live there; this file is the order of work and the run log).

## Tasks
1. Docs first (this file and the plan, README index rows), commit.
2. Test first: the prompt carries the follow-up rule, and still forbids writing without Confirm.
3. Add rule 9 to `app/assistant/prompt.py`; run `tests/assistant` and the security suites.
4. Re-run the live evaluation (`--runs 3`), apply the plan's section 4, then either keep (regenerate the report) or revert.
5. CHANGELOG, STATUS, questions rows, ASSUMED 54.

## Run log
| Step | Command | Result |
|---|---|---|
| Diagnosis | a probe wrapping `llm._post` for `go_ahead_after_check` (stop reason, block types, token counts only) | the model calls `check_purchase_risk` again (stop reason `tool_use`, blocks thinking, text, tool_use), then writes a long reply that the number check replaces |
| Rule 9 (prompt) tests first | `pytest tests/assistant/test_prompt.py` | red (follow-up test), then green; `tests/assistant`, `tests/test_assistant_eval.py`, `tests/test_run_security_drill.py` 211 passed |
| Re-run after rule 9 | `python scripts/assistant_eval.py --runs 3 --pause 1` | **38 / 39** (was 34 / 39): `go_ahead_after_check` 3 / 3, every other scenario unchanged at 3 / 3, `ambiguous` 2 / 3 (was 1 / 3, noisy), answers replaced by the number check 5 (was 4), p50 3.7 s / p95 6.7 s, 11,569 in / 446 out tokens a turn. The plan's section 4 holds. In all three `go_ahead_after_check` runs the proposal card appears but the model's sentence was replaced |
| Demo and live journey after rule 9 | `scripts/demo_run.py --api` (backend restarted with the evidence-run caps in the process environment: 2,000,000 per user, because the first demo run had used most of the day's 150,000 and the real caps then returned 429, which is the guard working); `playwright.live.config.ts` | "Go ahead with that." still "I could not work that out" against the real API. The stored fallbacks show why (section 6 of the plan): the model asked a clarifying question and the number check replaced it because `799` came from an earlier *user* turn |
