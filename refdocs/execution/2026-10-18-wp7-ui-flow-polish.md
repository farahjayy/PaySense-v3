# Execution — WP7 UI and flow polish

> Companion plan: `refdocs/plans/2026-10-18-wp7-ui-flow-polish.md`.

## Tasks
1. Tests: `LoginPage.test.tsx` (+2), `DashboardStrips.test.tsx` (4), `AssistantPanel.test.tsx` (+1 launcher), `ModelScreen.test.tsx` (C7 rows). Then `components/ui/LocalTerms.tsx`, login page, `lib/assistantLauncher.tsx`, `AppShell` provider, `AssistantPanel` `prompt`, `components/dashboard/TryThis.tsx`, `components/dashboard/BudgetStrip.tsx`, dashboard order.
2. `tests/e2e/layout.spec.ts` (phone project, 360 and 375 px, every screen and the assistant panel).
3. Screenshots (desktop and phone) reviewed; fixes.

## Deviations
- Found in screenshots and fixed: the forecast chart's y-axis labels wrapped at the space in "RM 650" and overlapped the month labels (no-break space, axis 76 px); the phone's "More pages" row wrapped "About the model" over three lines (no-wrap links, the row wraps instead).
- The first `prettier --write` was run on whole folders and reformatted files outside this package; those were reverted before committing, and prettier was then run only on the files changed here.

## Wrap-up
CHANGELOG, STATUS, DECISIONS (ASSUMED 41), questions; commit and push.
