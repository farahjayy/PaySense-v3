# Plan — WP7 UI and flow polish

> Execution: `refdocs/execution/2026-10-18-wp7-ui-flow-polish.md`. Scope: work-packages.md WP7.

## 1. Why this exists
A judge sees the first screen for seconds. It must say what PaySense does, show the student's position, and lead straight into the assistant story (afford → safest option → confirm), on a desktop and on a small phone, in words a reader outside Malaysia follows.

## 2. Scope
**In:** dashboard tagline; a "Try this" strip that opens the assistant with the demo question typed in (never sent for the person); a budget strip; the login page's stale "There is no password" line (WP18 added a passphrase), the responsible-use line and a "New to BNPL in Malaysia?" box (ringgit and sen, the three providers, PTPTN, allowances, why students use BNPL) also on the model page; a phone check at 360 and 375 px on every screen and the assistant panel; fixes for any glitch found in screenshots.
**Out:** a redesign; a colour change to the app theme.

## 3. Approach
The assistant launcher is a small context the app shell provides (`lib/assistantLauncher.tsx`); pages call it, the panel receives the question as its draft. The order of the dashboard follows the brief: headline, alerts, score and margin, then the "Try this" entry, then BNPL instalments, budgets and recent months. The context box has no figures (the login page test forbids figures that are not the user's own). PESP is named without expanding it (ASSUMED 41).

## 4. Definition of done
Unit tests for each new piece; axe rows green; Playwright desktop and phone pass, plus a layout spec asserting no sideways scroll at 360 and 375 px; build green; screenshots reviewed.
