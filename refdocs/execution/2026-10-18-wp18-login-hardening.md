# Execution — WP18 Login and abuse hardening

> Companion plan: `refdocs/plans/2026-10-18-wp18-login-hardening.md`.

## Before starting
WP-API landed. Migration numbering: the work packages name `0003_budgets_assistant.sql`; WP18 lands first (section 5: "land them early"), so it takes **0003** and budgets/assistant become **0004** (recorded in the changelog).

## Tasks
1. Migration `backend/migrations/0003_login_hardening.sql`; fake schema (`tests/fakes.py`: defaults, `user_locks`, `count`, `lt`). Verify: SQL parses; fake tests pass.
2. Passphrase module + tests (`tests/test_passphrase.py`). Verify: hash format, verify true/false, unknown-user path still hashes.
3. Login, logout, token version (`api/auth.py`, `core/security.py`, `api/deps.py`, `db/users.py`, `app/seed.py`, `scripts/seed_users.py --passphrase-file`, `scripts/seed_testers.py`). Tests in `tests/test_auth.py`. Verify: pass.
4. Write quota + ledger cap + route enumeration test (`tests/api/test_abuse_limits.py`). Verify: pass.
5. Pagination (`api/transactions.py`, `db/transactions.py`, `ScopedTable` keyset); frontend `useTransactions` follows the cursor. Verify: API test + Vitest.
6. Plan-create lock (`db/locks.py`; `api/risk.py`, `api/plans.py`). Verify: concurrent-confirm test.
7. Every login in tests and tools passes a passphrase (conftests, `e2e_server.py`, Playwright, `smoke_live.py`, `load_personas.py`, frontend `LoginForm`). Verify: full backend suite, Vitest, Playwright.

## Wrap-up
`gen:api`; CHANGELOG, STATUS, DECISIONS (`ASSUMED` sizes); questions.md (apply 0003); commit and push.
