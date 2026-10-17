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
