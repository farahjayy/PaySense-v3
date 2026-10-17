# Plan — WP18 Login and abuse hardening (D-49)

> Execution: `refdocs/execution/2026-10-18-wp18-login-hardening.md`. Scope: work-packages.md WP18; ADR D-49.

## 1. Why this exists
Username-only login (D-03) is the first thing a security reviewer raises, and the competition scores security at 30%. v2 also left abuse gaps open: tokens could not be revoked, nothing capped how much one account could write, the transaction list returned a whole range at once, and two server workers could both create the same plan.

## 2. What's already covered
HS256 tokens with a TTL; per-IP failed-login limiter; per-user request limiter (`rate_limited`); body-size limit; user scoping in `ScopedTable`; the in-process confirm lock and 120-second duplicate window in `api/risk.py`.

## 3. Scope
**In**
- **Passphrase factor:** `users.passphrase_hash` holding `scrypt$n$r$p$salt$hash` (n=2^14, r=8, p=1, 16-byte salt per user, `hashlib.scrypt`); set at seeding (`seed_users.py --passphrase-file`, or generated and printed once); login needs username **and** passphrase; `hmac.compare_digest`; one generic error for every failure (`invalid_credentials`); an unknown user still costs one scrypt (no timing oracle); a user with no passphrase cannot log in.
- **Login rate limits:** the per-IP limiter plus a per-username limiter (20 failures per 15 minutes).
- **Token revocation:** `users.token_version`; the token carries `ver`; `POST /auth/logout` increments it (every session of that user ends); `current_user` refuses a token whose `ver` is not the current one.
- **Write quota:** per user per Malaysian day, across every write route (ledger, plans, budgets, categories, recurring items, limits, assistant confirms); 429 `daily_write_quota` with `Retry-After` to midnight. A test enumerates every write route and fails if one lacks the quota.
- **Ledger cap:** at most `MAX_LEDGER_ROWS` transactions per user, checked in the repository (`transactions.create` / `bulk_create`), so no path can bypass it; 413 `ledger_full`.
- **Pagination:** `GET /transactions` takes `limit` (1–500, default 500) and an opaque keyset `cursor` (date, id), newest first; response `{transactions, next_cursor}`. The frontend follows the cursor.
- **Plan-create race:** a database row lock — table `user_locks (user_id, name)` primary key — taken before the duplicate check in `POST /risk/confirm` and `POST /plans`; a second worker gets 409; a lock older than 120 s is treated as abandoned.
- Migration `0003_login_hardening.sql` (columns, `user_locks`, keyset index), RLS on, privileges revoked; `check_rls.py` lists `user_locks`.

**Out, with reasons**
- Email/device second factor (no mail provider; D-49 rejected).
- Moving the month summary and used-limit into SQL aggregates (the "to confirm" item): they already read only four columns, and the ledger cap bounds the rows; an RPC would need a Postgres function the in-memory fake cannot run. `ASSUMED`, logged.
- A persistent (database) rate limiter and quota store: in-memory, single process, resets on restart — on the known-risk list (WP8).

## 4. Approach
One `app/core/passphrase.py`; `users.set_passphrase`, `users.bump_token_version`; `seed_user(..., passphrase=)`. `security.decode_access_token` returns `(user_id, version)`. `api/deps.write_quota` dependency backed by `DailyQuota` (in-memory, keyed by user and Malaysian date). `LedgerFullError` raised by the repository, mapped to 413 in `main.py`. `db/locks.py` (`acquire`, `release`, context manager).

## 5. Risks & unknowns
| Risk | Confidence | Mitigation |
|---|---|---|
| The per-username limiter lets a stranger lock a judge out by failing on purpose | High that it is possible | Higher threshold than per-IP, 15-minute window; on the known-risk list |
| The real database lacks the new columns until 0003 is applied | Certain | questions.md; real-database checks run after the author applies it |
| A stale lock after a crash blocks plan creation | Low | 120-second staleness rule |
| scrypt cost on a small Render instance | Medium | ~50 ms, 16 MB per login; login is rate limited |

## 6. Definition of done
Tests for each item (generic error, timing path for unknown users, per-username limit, logout revokes, version mismatch refused, quota on every write route, cap via every insert path, cursor pages without overlap or gaps, concurrent confirm refused by the lock), two-user and unauthenticated tests on changed routes, Playwright login updated; ruff, tsc, lint clean; types regenerated.
