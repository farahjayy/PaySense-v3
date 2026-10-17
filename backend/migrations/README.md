# Migrations

Numbered SQL files, applied **in order**, each exactly once, in the Supabase dashboard → SQL Editor.
The backend never runs migrations itself.

| File | What it does |
|---|---|
| `0001_init.sql` | All tables, composite `(id, user_id)` foreign keys, RLS on with no policies, anon/authenticated privileges revoked. Requires Postgres 15+ (Supabase default). |
| `0004_budgets_assistant.sql` | WP2: `budgets` (unique per user and lower(category)); WP4b adds `assistant_actions` and `assistant_events`. RLS on, privileges revoked. Apply after 0003. |
| `0003_login_hardening.sql` | WP18 (D-49): `users.passphrase_hash` and `users.token_version`, the `user_locks` table, the keyset index on transactions. RLS on, privileges revoked. **After applying, set a passphrase on every account** (`scripts/seed_users.py --passphrase-file`): a user without one cannot log in. |
| `0002_user_categories.sql` | `user_categories`: the categories a person adds themselves (the twelve built-in ones live in code). RLS on with no policies, privileges revoked. Apply after 0001, then run `check_rls.py`. |

Rules:
- A DB column or table change = a **new** numbered file plus the repository function and the Pydantic schema, in the same commit. Never edit an applied migration.
- Money columns are `bigint` sen (`*_sen`). Never `numeric` or `float`.
- After applying a migration, run `uv run python scripts/check_rls.py` (needs `SUPABASE_URL` and `SUPABASE_ANON_KEY`) to confirm the anon key still reads nothing.
