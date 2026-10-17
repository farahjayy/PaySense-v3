# Execution — WP5 Assistant frontend

> Companion plan: `refdocs/plans/2026-10-18-wp5-assistant-frontend.md`.

## Tasks
1. Tests first: `tests/unit/assistant.test.ts` (lib), `tests/unit/AssistantPanel.test.tsx`, `tests/unit/AssistantCards.test.tsx`. (Deviation: the axe checks live in the two component test files, over every card kind and over the panel in llm and guided mode, rather than in `a11y.test.tsx`.)
2. `lib/assistant.ts`, `lib/api/assistant.ts`, `components/assistant/*`, header button in `AppShell`. Verify: `npx vitest run`, `npx tsc --noEmit`, `npm run lint`.
3. e2e: `backend/tests/e2e_server.py` gains `assistant-guided` and `assistant-llm` journey accounts (consented, persona ledger preloaded) and an opt-in deterministic `ScriptedLLM` (`E2E_FAKE_LLM=1`, set by `playwright.config.ts`), given through a `get_llm` override to every tester except the `assistant-guided` ones, who stay in real guided mode. `backend/tests/test_e2e_server.py` covers the switch. `tests/e2e/assistant.spec.ts`. Verify: `PW_CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test`.

## As built (deviations)
- The quick actions and forms sit in one `<details>` "Quick actions and forms (no model)": open in guided mode, closed in llm mode. One element in both modes so an open form keeps its state when the status arrives.
- A link inside the panel to another screen closes the panel (on a phone it would cover the new screen).
- The bills card shows the frontend's own heading ("Bills and what is due"), not the server's card title.

## Wrap-up
Merge notes for CHANGELOG/STATUS in `refdocs/fintechathon-2026/wp5-merge-notes.md`; commit on the worktree branch.
