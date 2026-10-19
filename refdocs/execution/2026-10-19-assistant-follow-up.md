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
