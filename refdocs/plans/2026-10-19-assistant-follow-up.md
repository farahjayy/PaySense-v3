# Plan — The assistant's follow-up turns ("Go ahead with that.")

> Execution: `refdocs/execution/2026-10-19-assistant-follow-up.md`. Evidence: `reports/assistant/` (the 34 / 39 run on `claude-haiku-5-5`), `questions.md` rows 59-60.

## 1. Why this exists
The live evaluation, the demo run and the live browser journey all showed the same weakness: after the assistant has checked a purchase, "Go ahead with that." does not produce a plan proposal. Measured: `go_ahead_after_check` 0 / 3 on Haiku and 0 / 2 on Sonnet 5.5; "I could not work that out" in the demo and the browser journey. The explicit request ("Please add the RM799 SPayLater phone plan over 3 months") works every time (`go_ahead` 3 / 3).

## 2. Diagnosis (measured, not guessed)
A raw-response probe of the scenario (stop reason and block types only): the model does not return an empty answer. It calls `check_purchase_risk` again instead of `propose_action`, writes a long reply, and the number check replaces that reply with a template (`narration_replaced`). The system prompt has no rule for a follow-up that agrees to a purchase just discussed, and its rule 1 ("if you need a number, call a tool") together with earlier turns arriving as plain text (no tool results, by design) leads the model to verify again before acting.

## 3. Change (one rule, nothing else)
Add rule 9 to `SYSTEM_PROMPT`: when the user agrees to a purchase just discussed ("go ahead", "yes", "add it"), call `propose_action` with `create_plan` and the item, provider, price, instalments and date from the conversation; do not run the risk check first (the server runs it again before anything is saved); ask for a single detail only if one is missing. No tool, policy, tier or confirm change: the model still has no write tool and a proposal still needs the person's Confirm (D-48).

## 4. Acceptance rule (written before the re-run)
Same evaluation as before: 13 scenarios x 3 runs on `claude-haiku-5-5`, same success criteria (they are fixed in the script and are not touched).
1. `go_ahead_after_check` reaches at least 2 / 3.
2. No other scenario falls below its previous result (afford, safest, when, go_ahead, bills, insights, set_budget, add_transaction, import, out_of_scope, injection all 3 / 3; ambiguous 1 / 3 is noisy, so it must not fall below 1 / 3).
3. Total at least 36 / 39, and the security scenarios (`injection`, `out_of_scope`) and the security drill stay unchanged.

If any of the three fails, the rule is reverted and both runs are reported. If it passes, the report is regenerated and the 34 / 39 run stays in the changelog and in `questions.md` as the "before".

## 5. Risks
- A prompt that says "do not run the check" could make the model propose a plan for a purchase nobody discussed: the proposal still needs Confirm and the server re-checks before saving, and the rule only applies to a purchase just discussed. The security drill and the assistant security suites must stay green.
- One run of 3 per scenario is a small sample; the result is reported with that stated.

## 6. A second cause, found after the rule 9 re-run (the audit log, not a guess)
After rule 9 the evaluation reached 38 / 39, but the demo against the real API and the live browser journey still answered "I could not work that out" to "Go ahead with that." The stored `number_check` fallbacks (`assistant_events`, kind `fallback`) hold what the model wrote before it was replaced: a sensible clarifying question ("Do you want me to prepare the RM799 SPayLater plan over 3 months anyway, even though the risk check rates it At Risk?"), replaced because `799` was "unsupported". The number check allows figures from tool results, the step summaries and the **current** message only (`person = [body.message, body.pasted_text]` in `agent.py`), so a price the student typed in an earlier turn of the same conversation counts as invented. That is a defect in the guard, not in the model: the student's own words are a legitimate source, and a template that hides a correct question is worse than the figure it blocks.

### Change
`person` also includes the text of the **user** turns in the request's `history`. The assistant's earlier turns stay untrusted: a figure that only an earlier assistant reply contains is still replaced (that is the case the guard exists for). The history is client-supplied, but it can only whitelist numbers the signed-in student wrote themselves, exactly as the current message already can.

### Acceptance (written before the change)
1. Unit tests (red first): a figure from a user history turn passes; the same figure only in an assistant history turn is replaced; a figure in neither is replaced.
2. The same 39-turn evaluation: total at least 38 / 39, no scenario below its result in the rule 9 run, and the number of answers replaced by the number check lower than in that run (5).
3. `injection`, `out_of_scope` and the security drill unchanged; `tests/assistant` and `tests/security` green.
4. The demo against the real API: "Go ahead with that." produces an answer or a proposal, not "I could not work that out".

## 7. The run after the number-check change, and a third cause
The evaluation after section 6's change gave **36 / 39**, so **section 6's criterion 2 (at least 38 / 39, no scenario below the rule 9 run) failed as written**: `go_ahead_after_check` 3 / 3 and answers replaced 4 (< 5) held, but `ambiguous` fell to 0 / 3 (it was 2 / 3 after rule 9 and 1 / 3 before). That scenario has no earlier turns, so section 6's change cannot touch its path; I did not call it noise but looked: a six-run probe of that scenario (model text and number-check flags only) shows the model asks the right clarifying question in every run, and in four of six it also says "today (2025-12-29)", the date the system prompt gave it, which the number check flags (`2025`, `29`) and replaces with a template. That is a second false positive in the guard: today's date is a fact the app itself supplied.

### Change
Today's date (ISO) joins the trusted sources for the number check, next to the student's own words. A different date the model writes (tomorrow, a due date it computed) is still flagged.

### Acceptance (written before the change)
1. Unit tests (red first): today's date in the model's text passes; a different date is replaced.
2. The same 39-turn evaluation: `ambiguous` at least 2 / 3, every other scenario at 3 / 3, total at least 38 / 39, answers replaced by the number check below 4.
3. `tests/assistant` and `tests/security` green; the security drill unchanged.
4. The demo against the real API: "Go ahead with that." gives an answer or a proposal, not "I could not work that out".
If 2 fails again, the result is reported as it is and the author decides; nothing further is changed in this round. Section 6's failed criterion stays recorded as failed: the change it covers is kept because its own cause is proven (the stored `number_check` fallbacks), not because the rule was reinterpreted.
