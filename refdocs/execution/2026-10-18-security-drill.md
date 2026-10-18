# Execution — The security drill ("judge mode")

> Companion plan: `refdocs/plans/2026-10-18-security-drill.md`.

## Tasks
1. Move the in-memory database to `backend/app/db/memory.py`; `tests/fakes.py` re-exports it (no behaviour change; the whole suite stays green).
2. Tests first: `backend/tests/security/test_drill.py` — every attack in the plan's table runs, at least three per class, none causes harm; a control switched off in the test (monkeypatched) shows up as harm; the caller's database is unchanged; two runs give the same scoreboard.
3. `backend/app/security/drill.py` (sandbox, hostile scripts, harm checks) and `backend/app/api/security.py` (`POST /api/security/drill`, auth, rate limit, not a write); API tests incl. 401 and 429; `NOT_WRITES` in the quota test.
4. `npm run gen:api`; frontend `/security` screen (scoreboard per class, expandable attacks), nav link; Vitest, axe, Playwright.
5. Docs: ADR D-58, CHANGELOG, STATUS, SECURITY.md pointer, demo video script line.

## As built
All five tasks done (CHANGELOG, "The security drill on screen (D-58)"). One deviation: a smuggled-id call that runs is not harm by itself (tools always run for the signed-in user); only the other student's marker data appearing is.
