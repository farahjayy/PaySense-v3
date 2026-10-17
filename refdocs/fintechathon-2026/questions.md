# Questions for the author

> Collected during the autonomous build of WP0–WP19. Each item says what was assumed (if anything) so work could continue, and what the author needs to do or decide. Ordered by package.

| # | Package | Question / action | What was done meanwhile |
|---|---|---|---|
| 1 | WP0 | Tag `fyp-final` on the FYP repo (author's machine). | Nothing in this repo depends on it. |
| 2 | WP1 | `scripts/check_rls.py` needs `SUPABASE_ANON_KEY` (the anon/publishable key), which is not in this environment. Run it once after each migration, or add the key to the environment. | Checked that a request with no key is refused (HTTP 401) on `users`; the anon-key check itself was not run. |
| 3 | WP1 | With the current (v1) risk model, **no purchase in the demo grid comes back Safe** and no smallest change reaches Safe, for any persona — even before the purchase the persona ledgers show a 0.32–0.67 chance of a shortfall (`refdocs/fintechathon-2026/demo-scenario.md`). The demo script's step 9 ("a small purchase on the budget-conscious persona comes back Safe") cannot be shown on this model. | Reported as found; re-run after WP16. |
| 4 | WP18 | **Apply migration 0003 (`backend/migrations/0003_login_hardening.sql`) in the Supabase SQL editor.** Until it is applied the code on this branch cannot log anyone in on the real database (it reads `users.passphrase_hash` and `token_version`). After applying: re-run `scripts/load_personas.py` (it generates and stores a passphrase per persona account in `data/private/persona_accounts.json`) and `check_rls.py`. | Built and tested on the in-memory database; real-database checks deferred to the final step. |
| 5 | WP18 | Confirm the sizes in ASSUMED 18 (300 writes/day, 5,000 rows, 20 failed logins per username per 15 minutes) and 22 (per-username lockout trade-off). | Used as written. |
| 6 | WP18 | The work packages name the budgets/assistant migration `0003_budgets_assistant.sql`; WP18 landed first (section 5 says to land it early), so login hardening is **0003** and budgets/assistant will be **0004**. | Numbered in the order written. |
| 7 | WP2 | **Apply migration 0004 (`backend/migrations/0004_budgets_assistant.sql`)** after 0003. It will also hold the assistant tables (WP4b) — apply the final version from the branch head. Then run `uv run pytest -m integration` (the `test_v3_migrations.py` tests skip until it is applied). | Built and tested on the in-memory database. |
| 8 | WP2 | Confirm ASSUMED 20: near at 80%, over at 100%, a 10% buffer, three months of history, limits rounded down to RM5. | Used as written. |
| 9 | WP14 | Confirm ASSUMED 23 (unusual = above median + 3 robust SDs, 5+ earlier rows) and 24 (savings rate = left over ÷ income; money set aside as Savings shown separately). | Used as written. |
| 10 | WP15 | Confirm ASSUMED 25: an alert for an At Risk forecast only (Caution is a recommendation); limit nearly used at 80%. | Used as written. |
| 11 | WP1/WP15 | `load_personas.py` confirms every recurring item the app detects, as a tester pressing Confirm on each would. On frequent_bnpl that includes "SPayLater instalment …" rows (a BNPL plan the persona never entered as a plan), so they count as a monthly bill. Should the demo accounts confirm only some suggestions, or should the persona have its plans entered? | Left as the detector suggests. |
