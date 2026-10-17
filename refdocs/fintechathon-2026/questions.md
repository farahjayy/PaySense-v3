# Questions for the author

> Collected during the autonomous build of WP0–WP19. Each item says what was assumed (if anything) so work could continue, and what the author needs to do or decide. Ordered by package.

| # | Package | Question / action | What was done meanwhile |
|---|---|---|---|
| 1 | WP0 | Tag `fyp-final` on the FYP repo (author's machine). | Nothing in this repo depends on it. |
| 2 | WP1 | `scripts/check_rls.py` needs `SUPABASE_ANON_KEY` (the anon/publishable key), which is not in this environment. Run it once after each migration, or add the key to the environment. | Checked that a request with no key is refused (HTTP 401) on `users`; the anon-key check itself was not run. |
| 3 | WP1 | With the current (v1) risk model, **no purchase in the demo grid comes back Safe** and no smallest change reaches Safe, for any persona — even before the purchase the persona ledgers show a 0.32–0.67 chance of a shortfall (`refdocs/fintechathon-2026/demo-scenario.md`). The demo script's step 9 ("a small purchase on the budget-conscious persona comes back Safe") cannot be shown on this model. | Reported as found; re-run after WP16. |
