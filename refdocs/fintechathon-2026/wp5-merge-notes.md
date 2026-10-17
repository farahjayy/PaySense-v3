# WP5 merge notes (assistant frontend)

Built in a worktree branch. These are the pieces the merging session copies into the files a fork
does not edit (`CHANGELOG.md`, `STATUS.md`, `DECISIONS.md`, `questions.md`); delete this file once
they are merged.

## CHANGELOG entry

```
### 2026-10-18 — WP5 assistant frontend
- **Changed:** `frontend/lib/assistant.ts` (pure helpers: tier labels, proposal titles, history trimming, input and source formatting, error-to-state mapping, demo prompts, quick actions, guided form builders that turn typed ringgit into sen through `parseRm`) and `frontend/lib/api/assistant.ts` (status, opening, chat, run, confirm and decline hooks; Confirm refreshes the ledger, budgets, insights, recommendations, alerts and the assistant status). `components/assistant/`: `AssistantPanel` (side panel on desktop, full screen on a phone; opening turn from `/assistant/opening`; suggested prompts; paste box; states for loading, consent required with a link to /account, daily budget used, rate limited, offline, error), `AssistantMessage` ("What I did" steps with Read / Worked out / Needs your OK), `ResultCard` (every card kind; reuses RiskResult, PlanPreviewPanel, BillsDue), `ConfirmCard` (built from the stored proposal, Confirm / Cancel, 410 expired and 409 already used say to ask again), `GuidedActions` (quick actions and four forms: check a purchase, set a budget, add a transaction, paste). "Ask PaySense" button in the AppShell header (NAV_ITEMS untouched); `Button` takes a `ref`; `useInvalidateLedger` exported. Backend test tooling only: `tests/e2e_server.py` gains `assistant-guided` / `assistant-llm` accounts (consented, persona ledger preloaded) and an opt-in deterministic `ScriptedLLM` (`E2E_FAKE_LLM=1`, never a real provider) given through a `get_llm` override to every tester but the guided ones; `tests/test_e2e_server.py`. `playwright.config.ts` sets `E2E_FAKE_LLM=1`; `tests/e2e/assistant.spec.ts`.
- **Decided:** ASSUMED 50–54 below.
- **Deviations:** quick actions and forms are reachable in llm mode too (a closed disclosure); axe checks live in the component test files; the bills card keeps the frontend's own heading.
- **Verified:** `cd frontend && npm run lint` clean; `npx tsc --noEmit` clean; `npx vitest run` 39 files, 362 tests passed; `npx vitest run --coverage` lib 99.31% statements / 96.59% branches / 100% functions / 100% lines, all files 90.29%; `npm run build` succeeded; `PW_CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test` 20 passed (the 4 new assistant journeys, desktop and phone, plus the 16 existing). `cd backend && uv sync && uv run ruff check .` all checks passed; `uv run ruff format --check .` 324 files already formatted; `uv run pytest tests/test_smoke_live.py tests/test_load_personas.py tests/test_e2e_server.py -q` 16 passed; `uv run pytest tests/assistant tests/test_find_demo_scenario.py tests/test_e2e_server.py -q` 176 passed.
- **Known issues / next steps:** a quick action's chat bubble shows the tool name ("Get bill analysis"), not the button's words; the full-screen phone panel is `aria-modal="false"` (focus is not trapped); the live model has not driven the panel in a browser (only the scripted one).
```

## STATUS row

```
| C5 Assistant frontend (WP5) | Panel, cards, confirm card, guided mode, states, a11y | ✅ Done on the in-memory backend — Vitest 362 (lib 99% lines), axe clean on every card and the panel, Playwright 20 incl. guided and scripted-model journeys on desktop and phone. Not run: the panel against a live model |
```

## ASSUMED items (for DECISIONS.md)

- **ASSUMED 50:** the quick actions and forms are also offered in llm mode, behind a closed "Quick actions and forms (no model)" disclosure (open in guided mode). They run the same Tier 0/1 tools with no model call, so they cost no tokens and give a judge a path that works even if the model misbehaves.
- **ASSUMED 51:** a link inside the panel to another screen closes the panel, since on a phone it covers the whole screen. On desktop this also closes it; the conversation is not kept.
- **ASSUMED 52:** the guided forms date a purchase or transaction with the browser's today (`todayIso`), the same as the existing risk and transaction forms; the server validates it.
- **ASSUMED 53:** an expired (410) or already-used (409) proposal shows "Ask again to get a fresh one" as text in the card rather than a button that re-sends the last message, so nothing is re-proposed without the user typing or tapping again.
- **ASSUMED 54:** the Playwright backend picks the model per tester through a `get_llm` dependency override, so one server serves both the guided journey (no model, the real guided reason) and the llm journey (scripted model). Test tooling only.

## Questions for the author

1. Should the quick actions stay visible in llm mode (ASSUMED 50), or appear only in guided mode as the brief listed them?
2. On a phone the panel fills the screen but is not a modal dialog for screen readers. Should it become `aria-modal` with a focus trap there (desktop keeps the side panel non-modal)?
