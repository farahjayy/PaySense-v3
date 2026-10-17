# Plan — WP4a Assistant tool layer (no LLM yet)

> Execution: `refdocs/execution/2026-10-18-wp4a-tool-layer.md`. Scope: work-packages.md WP4a, section 3.1; ADRs D-47, D-48.

## 1. Why this exists
The assistant must reach the same engines and rules as the screens, through a small, typed, permissioned surface the model can call — and nothing else. Building the tool layer before any LLM means it can be tested deterministically and used by guided mode (buttons and forms) with no model at all.

## 2. What's already covered
Every capability exists as a shared function the routes call: `forecast_for`, `check_for`, `propose_for`/`preview_out`, `status_for`/`suggest_for`/`list_for`, `bills_for`, `spending_for`, `recommendations_for`, `limits_for`, the summary and transactions repositories. The WP-API contract defines the card shapes.

## 3. Scope
**In:** `backend/app/assistant/`: `context.py` (who and when — `user_id` only from the session), `tools.py` (registry: name, tier, description, Pydantic input model → JSON schema, handler returning a typed card), `policy.py` (tier rules), `executor.py` (validate, enforce policy, run, record a step). Tier 0 tools: `get_month_summary`, `get_spending_by_category`, `list_recent_transactions` (bounded, descriptions optionally redacted), `get_bills_by_month`, `get_bill_analysis`, `get_spending_insights`, `get_forecast`, `list_plans`, `list_providers_and_limits`, `get_budgets`, `get_budget_status`, `get_recommendations`, `get_alerts`. Tier 1: `check_purchase_risk`, `preview_plan`, `suggest_budget` (and, in WP4b/WP4d, `propose_action`, `parse_pasted_transactions`). `POST /api/assistant/run` (guided mode) on top.
**Out:** pending actions and Tier 2 writes (WP4b), the LLM loop (WP4c), paste parsing (WP4d).

## 4. Approach
- Handlers call the shared functions in process — never HTTP, never copied logic.
- **Tier 2 functions are not in the model's registry at all.** They live in a separate registry that only the confirm endpoint can reach (WP4b). The executor also refuses any tool whose tier is above what the caller may use, so registering a write by mistake still cannot run it from the model path.
- Inputs are Pydantic models with `extra="forbid"`; any `user_id` key anywhere in the arguments is refused before validation.
- Errors from the shared functions (a 422 for a bad purchase date, a 503 when the risk model is busy) become a step with status `error` and the server's own message — never an exception to the model.
- Isolation: a test seeds two users with distinctive data and runs every tool as the other user.

## 5. Risks & unknowns
| Risk | Confidence | Mitigation |
|---|---|---|
| JSON schemas from Pydantic use `$ref`/`anyOf` that some providers reject | High | Each LLM adapter flattens schemas (WP4c); the registry keeps the Pydantic source |
| A Tier 0 tool leaks too much ledger to the provider | Medium | `list_recent_transactions` capped at 20 rows / 90 days; descriptions redactable by setting |

## 6. Definition of done
Every tool has a unit test; the policy test proves a Tier 2 tool cannot run through the model path; `user_id` in arguments is rejected; two-user isolation holds for every tool.
