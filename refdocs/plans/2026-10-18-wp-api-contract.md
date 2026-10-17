# Plan — WP-API Contract first

> Execution: `refdocs/execution/2026-10-18-wp-api-contract.md`. Scope: work-packages.md WP-API.

## 1. Why this exists
The frontend lane (WP3, WP5) must not wait for the backend lanes. The OpenAPI document is the contract (D-18); landing the shapes as stub routes and regenerating `schema.d.ts` lets both sides build against the same types.

## 2. What's already covered
The existing response models (`RiskCheckOut`, `ForecastOut`, `PlanPreviewOut`, `BillsOut`, `MonthSummaryOut`, `CategorySummaryOut`, `TransactionIn`, `ConfirmIn`, `PlanIn`) — the assistant's cards and pending actions reuse them rather than re-describing them.

## 3. Scope
**In:** request and response models and stub routes (HTTP 501 `not_implemented`) for `/budgets` (list, `PUT` with the name in the body, `DELETE ?category=`, `/status?month=`, `/suggest`), `/insights/bills`, `/insights/spending?month=`, `/recommendations`, `/alerts`, `/assistant/status`, `/assistant/opening`, `/assistant/chat`, `/assistant/run` (guided mode: one Tier 0/1 tool from a button or form), `/assistant/actions/{id}` (read), `/confirm`, `/decline`. `gen:api`.
**Out:** behaviour (each package fills its routes in); WP18/WP19 routes (logout, passphrase, account export/delete, settings) — added by those packages with their own contract change.

## 4. Approach
- Category names never travel in the path (D-43): `PUT /budgets` takes `{category, limit_sen}`; delete takes `?category=`.
- Assistant cards are a **discriminated union on `kind`**, each wrapping an existing response model, so the frontend renders a risk card with the same component and type as the risk screen. Pending actions are a discriminated union on `type` whose `payload` is the API's own request model (D-48: the confirm card is built from the validated payload).
- Chat history is `{role, text}` only, `additionalProperties: false`: tool results can never come from the client.
- No request model has a `user_id` field.
- Money stays integer `*_sen`; the existing money-contract test guards every new schema (it caught a float named `share_of_income`, renamed `bills_share`).

## 5. Risks & unknowns
| Risk | Confidence | Mitigation |
|---|---|---|
| A shape changes when the package is built | Medium | Each package regenerates the types and the drift check catches stale ones |
| Discriminated unions generate awkward TypeScript | Low | Checked: `oneOf` with `$ref`s, narrowed on `kind`/`type` |

## 6. Definition of done
Every new route is in `/openapi.json` and refuses a request without a session (401); the card and action unions are typed; `npm run gen:api` regenerated `schema.d.ts`; `tsc` clean.
