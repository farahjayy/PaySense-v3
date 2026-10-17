# Plan — WP5 Assistant frontend

> Execution: `refdocs/execution/2026-10-18-wp5-assistant-frontend.md`. Scope: work-packages.md WP5; ADRs D-47, D-48, D-53.

## 1. Why this exists
The assistant backend (WP4a–WP4d) is only judged through what a person sees: a chat that shows what it did, the engines' results as the app's own cards, and a confirm card that is the only way a change happens.

## 2. What's already covered
The assistant API (`/api/assistant/status|opening|chat|run|actions/*`), typed card and action unions in `lib/api/schema.d.ts`, the risk components (`RiskResult`, `SuggestionCard`, `WithWithoutChart`, `PlanPreviewPanel`), `BillsDue`, money and date formatters, the UI kit.

## 3. Scope
**In:** `lib/assistant.ts` (pure helpers: tier and status labels, history trimming to the last 8 plain-text turns, suggested prompts, quick actions, guided-form argument builders that turn typed ringgit into sen with `parseRm`, error → state mapping, source-figure formatting); `lib/api/assistant.ts` (TanStack Query hooks); `components/assistant/` (`AssistantPanel`, `AssistantMessage`, `StepsList`, `ResultCard` for every card kind, `ConfirmCard`, `GuidedActions`); an "Ask PaySense" button in the app header. States: loading, error, rate limited, daily budget used, consent required (link to `/account`), locked (the risk card's own locked state), offline. Responsible-use line in the panel.
**Out:** streaming replies; the consent page itself (main session); multi-conversation history (one conversation per open panel, kept in memory).

## 4. Approach
- The panel holds the conversation in component state and sends only `{role, text}` turns (the last 8) with each message; cards and steps are never sent back.
- Cards are rendered by `kind` from the typed union; the risk card is `RiskResult` itself, so a judge sees the same result as the risk screen.
- The confirm card is built from the pending action's `summary`, validated `payload` and (for a plan) the server's `preview`; Confirm/Cancel call the confirm/decline endpoints. A 409 says it was already used; a 410 says it expired and to ask again.
- Guided mode is the same panel: quick actions and small forms call `/assistant/run` with the same tools, so cards and confirmations are identical. It is offered whenever the status says guided, and after a consent, budget or rate-limit refusal.
- No money is computed: amounts arrive in sen and are formatted; typed amounts in forms go through `parseRm`.

## 5. Risks & unknowns
| Risk | Confidence | Mitigation |
|---|---|---|
| Large cards in a narrow side panel | Medium | Panel is wide on desktop, full screen on phones; cards are compact apart from the risk result |
| Playwright needs an LLM | Certain | Opt-in deterministic fake model in the e2e server (`E2E_FAKE_LLM=1`) |

## 6. Definition of done
Vitest for every component and `lib` file (≥ 80% on `lib`), axe clean; Playwright journeys in guided and llm mode on desktop and phone.
