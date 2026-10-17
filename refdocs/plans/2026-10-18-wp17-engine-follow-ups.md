# Plan — WP17 Engine follow-ups (C1, C4, C7)

> Execution: `refdocs/execution/2026-10-18-wp17-engine-follow-ups.md`. Scope: work-packages.md WP17.

## 1. Why this exists
Judges read the model page and the honest limits before they trust a score. After WP16 the limits changed (savings are now counted when entered; the band is recalibrated), so the page and the paragraph must say what is true now.

## 2. Scope
**In:** C1 — the honest-limits paragraph with every figure traced to a generated report (`refdocs/fintechathon-2026/honest-limits.md`, written in WP16). C7 — the in-app model page: competition framing, what the score never uses (age, gender, ethnicity, nationality, employment; repayment history shown, never scored), the assistant's limits (no figure of its own, propose-only, provider sees what it needs), and the honest limits in plain words without numbers (the page has no build step that could keep numbers current). C4 — a question to the author for a real checkout example.
**Out:** changing provider rules without a real checkout.

## 3. Approach
The page stays static and number-free, as the v2 card was; the numbers live in the paragraph, which names the report behind each. The fairness statement was checked against `FEATURE_ORDER` in `backend/app/engines/risk/features.py` (17 money-only features).

## 4. Definition of done
`ModelScreen.test.tsx` asserts each new statement; axe clean; questions.md row for C4.
