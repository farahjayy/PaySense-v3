# Plan — WP4b Pending actions, confirm endpoint, audit log

> Execution: `refdocs/execution/2026-10-18-wp4b-pending-actions.md`. Scope: work-packages.md WP4b, section 3.2; ADR D-48.

## 1. Why this exists
The model must never write. The only way the assistant can change anything is to *propose* it; the server stores the validated proposal, the person sees a card built from that stored payload, and only their button press runs the write — once. Every step is recorded so a judge (and the author) can see exactly what happened.

## 2. What's already covered
The five write paths as shared functions (`writes.py`: `create_for`, `import_rows_for`, `confirm_for`, `set_for`, `delete_for`); the plan-create lock and duplicate window (`api/risk.py`, D-49); the write quota.

## 3. Scope
**In:** tables `assistant_actions` and `assistant_events` in `0004_budgets_assistant.sql` (RLS on, privileges revoked); repositories with fakes; the Tier 1 tool `propose_action(type, payload)`; `GET /assistant/actions/{id}`, `POST …/confirm`, `POST …/decline`; audit rows for every proposal, confirm, decline, refusal and failure (WP4c adds messages, tool calls and fallbacks).
**Out:** `confirm_import` proposals from `propose_action` (only the paste parser may create them, WP4d, so every imported row is grounded first).

## 4. Approach
- **Propose:** the payload is validated with the API's own model for that write (`TransactionIn`, `PlanIn`, `BudgetIn`, `BudgetDeleteIn`), plus the checks the route would make (own recurring item, a budget category that can have a budget, the plan's provider rules and limit — whose preview is stored for the card). The server writes the summary sentence from the validated payload; a SHA-256 digest of the canonical payload is stored. An identical pending proposal is reused, not duplicated. Expiry: `ASSISTANT_ACTION_TTL_MINUTES` (10, `ASSUMED` 17).
- **Confirm:** same user (the row is read through `ScopedTable`); not expired (else marked `expired`, 410); still pending — claimed by an **atomic status change** (`update … where status = 'pending'`), so a replay or a double click gets 409; the stored payload is re-validated and its digest re-checked (a tampered row is refused and marked `failed`); a per-user confirm lock and a 120-second duplicate window (same type and digest confirmed recently) mirror `risk.py`. Then the Tier 2 function runs; if it fails the action is marked `failed` with the reason. Rate limited and counted against the write quota.
- **Decline:** atomic pending → declined.
- **Audit:** `assistant_events(user_id, kind, tier, tool, status, action_id, provider, model, input_tokens, output_tokens, detail)`; never the API key; free text truncated. `transactions.source` keeps its current values (the origin is in the audit log).

## 5. Risks & unknowns
| Risk | Confidence | Mitigation |
|---|---|---|
| A crash between claim and write leaves an action "confirmed" with nothing written | Low | The write's own guards (lock, duplicate window) make a re-proposal safe; the audit row shows the failure |
| Ten minutes is too short for a slow reader | Medium | `ASSUMED` 17; a new proposal is one click away |

## 6. Definition of done
Replay, expiry, wrong-user, double-confirm and tampered-payload tests pass; every confirm writes an audit row; two-user and unauthenticated tests on every route.
