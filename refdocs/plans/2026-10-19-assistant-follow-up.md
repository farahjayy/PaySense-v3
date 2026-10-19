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
