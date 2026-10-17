# Plan — WP3 Budgets, insights and recommendations screens (with WP19's screens)

> Execution: `refdocs/execution/2026-10-18-wp3-topic-screens.md`. Scope: work-packages.md WP3, and the frontend half of WP19.

## 1. Why this exists
The Topic A backend (WP2, WP13–WP15) needs screens a student and a judge can use without the assistant, and the privacy notice and data controls (WP19) need a place in the app.

## 2. What's already covered
The design system (`components/ui`), month stepper, money and date formatting, the generated API types, the risk components.

## 3. Scope
**In:** `/budgets` (list with bars, state in words and glyphs, money, pace; change, remove with confirmation; add; "Suggest a budget" with the working shown and "Use this" per category); `/insights` (ranked recommendations with "where these figures come from" and their action — a link, or a budget proposal that saves only after Confirm; bill analysis with collisions, increases and overdue items highlighted; spending insights with a month stepper, headline, movers, unusual transactions and every category); a dashboard alert strip; `/account` ("Your data": the notice, download, delete with the typed phrase and the passphrase); the first-login consent gate; nav entries. Loading, empty, error states; phone layout; axe.
**Out:** the assistant panel (WP5, built in parallel); visual polish across every screen (WP7).

## 4. Approach
Hooks in `lib/api/topic.ts` (separate from `queries.ts` so the parallel assistant work does not collide); pure helpers in `lib/budgets.ts` and `lib/insights.ts`. The budgets screen asks the server for "the current month" (Malaysian time) instead of computing it in the browser — found by the browser test, whose server runs on a pinned date. The consent gate fails open if the notice cannot load: the server enforces consent where it matters (the assistant's model call).

## 5. Risks & unknowns
| Risk | Confidence | Mitigation |
|---|---|---|
| Recommendations run the forecast on every visit | Medium | Same per-user limit as the forecast route; TanStack Query caches |

## 6. Definition of done
Vitest for screens and `lib/`, axe clean on the new screens, Playwright (set budget → add expense → bar changes; alert appears; consent on first login) on desktop and phone.
