# Execution — WP5 Assistant frontend

> Companion plan: `refdocs/plans/2026-10-18-wp5-assistant-frontend.md`.

## Tasks
1. Tests first: `tests/unit/assistant.test.ts` (lib), `tests/unit/AssistantPanel.test.tsx`, `tests/unit/AssistantCards.test.tsx`, axe in `tests/unit/a11y.test.tsx`.
2. `lib/assistant.ts`, `lib/api/assistant.ts`, `components/assistant/*`, header button in `AppShell`. Verify: `npx vitest run`, `npx tsc --noEmit`, `npm run lint`.
3. e2e: `backend/tests/e2e_server.py` gains the `assistant` journey accounts and an opt-in fake model (`E2E_FAKE_LLM=1`); `tests/e2e/assistant.spec.ts`. Verify: `PW_CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test`.

## Wrap-up
Merge notes for CHANGELOG/STATUS in `refdocs/fintechathon-2026/wp5-merge-notes.md`; commit on the worktree branch.
