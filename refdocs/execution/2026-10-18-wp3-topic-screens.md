# Execution — WP3 Topic screens (and WP19 screens)

> Companion plan: `refdocs/plans/2026-10-18-wp3-topic-screens.md`.

## Tasks
1. `lib/api/topic.ts`, `lib/budgets.ts`, `lib/insights.ts` + unit tests. ✅
2. `BudgetsScreen`, `InsightsScreen`, `AccountScreen`, `ConsentGate`, `AlertStrip`; routes `/budgets`, `/insights`, `/account`; nav. Tests: `BudgetsScreen.test.tsx`, `InsightsScreen.test.tsx`, `AccountScreen.test.tsx`; axe rows for the three screens. ✅
3. Deviation: `GET /budgets/status` month made optional (server's current month), found by the browser test. ✅
4. Playwright `tests/e2e/topic.spec.ts` (consent; budget → expense → bar → alert), desktop and phone. ✅
