# Architectural Decisions — PaySense v2

> Record decisions here so they aren't re-debated in future sessions.
> Format: **Decision** → **Why** → **Trade-offs / what was rejected**.
> Canonical one-line list lives in `refdocs/paysense-v2-PRD.md` §7; this file expands the load-bearing ones under the same id.

An ADR is worth writing when the decision (a) is expensive to reverse, (b) will look arbitrary to a future reader, or (c) had a real alternative someone will propose again. Everything else is just a commit message.

---

## D-01 — New public repo; v1 frozen; port proven modules with their tests
*2026-10-08 · author decision (scaffold interview)*

**Decision.** PaySense v2 lives in its own public repo. v1 (`../PaySense/`) is a read-only reference. Domain modules that are correct and tested in v1 (schedule, providers, ledger, plans, bills, categorize, CSV import, the Engine 2 CV harness, the frontend UI kit) are ported together with their tests; the engines, seed script and model artefacts are not.
**Why.** v1 was the experiment and accumulated 19 concept-document revisions of patches. Its domain code survived real use; its engines did not (see `context/v1-lessons.md`).
**Rejected.** Evolving v1 in place (drags the single-user schema, the personal-data history and the patched engines along); rewriting everything from scratch (re-learns solved problems such as sen rounding and provider start dates).

## D-03 — Username-only login, user-scoped repository layer
*2026-10-08 · supervisor decision, implementation by Claude*

**Decision.** `POST /api/auth/login {username}` looks up a pre-seeded user and returns a signed HS256 bearer token (secret from `SESSION_SECRET`, expiry 12 h). The frontend keeps it in `sessionStorage` and sends `Authorization: Bearer`. Every repository function takes `user_id` as its first argument; no query exists without it. The backend alone talks to Supabase (service key); RLS is enabled on every table with no policies for `anon`/`authenticated`, so a leaked anon key reads nothing.
**Why.** The supervisor ruled passwords and sign-up out of scope; each tester still needs isolated data. A bearer header avoids third-party-cookie problems between a Vercel origin and a Render origin.
**Trade-off.** Anyone who knows a username can log in as that user. Acceptable for a 5–7-person UAT on synthetic persona data; stated as a limitation and in the model card. Rejected: Supabase Auth (needs email/password or OAuth — out of scope), a profile picker with no login (supervisor asked for a username entry).

## D-04 — Engine 1 is a component forecaster with Monte Carlo uncertainty
*2026-10-08 · approved by author*

**Decision.** Known flows (confirmed recurring income and bills, BNPL instalments, dated savings goals) are placed on their exact dates. Only weekly discretionary spend is forecast. A residual-bootstrap Monte Carlo (1,000 paths, daily resolution, day-of-week spreading) produces P10/P50/P90 balances and P(shortfall). Everything is anchored to today.
**Why.** v1 forecast monthly *net* cash flow as one series: it decayed to zero, back-derived income bars from the net, collapsed to a flat line after one one-off entry, ignored stale logs, and lost to naive baselines. Banks split fixed and variable flows in production (BBVA, Monzo, Yodlee) and alert on P(negative balance) (BBVA, Intuit Mint ODEWS) — research §A.
**Rejected.** Daily discretionary forecasting (too noisy for a few months of data); per-category forecasting (too few points per category; possible future work); conformal intervals (residual bootstrap gives full paths, which the daily balance and P(shortfall) need).

## D-05 — Candidate algorithms stay within the literature review
*2026-10-08 · author asked for a recommendation; Claude recommended, author's earlier "full v2" choice of Chronos + EBM superseded*

**Decision.**
- Financial health forecasting candidates: **ARIMA, Prophet, LSTM** — plus **naive** and **moving-average** benchmarks. The LSTM is trained **globally** across many series (Berka / MoneyData / synthetic cohort) and applied per user.
- BNPL risk classification candidates: **Random Forest, XGBoost, LightGBM**, each with **monotonic constraints** — plus a **logistic-regression** benchmark.
- XAI: **SHAP**, plus counterfactual search.
**Why.** The literature review (supervisor-reviewed) selected these candidates; the methodology must follow from it, and Chapter 2 should not need new sections. Benchmarks are standard evaluation practice (fpp3; M4/M5), monotonic constraints are a model *configuration* (one methodology citation), and a global LSTM is how recurrent networks are normally applied to many short series. v1's failures were in design (target, label, features, evaluation), not in the choice of algorithms.
**Rejected (recorded as future work in the sources doc):** ETS/Theta, Chronos-2 / TimesFM / Moirai foundation models, Explainable Boosting Machines, WoE scorecards. Each would need new literature to justify.

## D-06 — Engine 1 selection rule
*2026-10-08 · Claude decision*

**Decision.** Rolling-origin evaluation on the weekly discretionary series (minimum training 26 weeks, step 4 weeks, horizons 4/8/13). Primary metric: MASE pooled across series. Also RMSSE, 80% interval coverage, end-of-horizon balance MAE. Significance: Harvey–Leybourne–Newbold-corrected Diebold–Mariano on pooled losses, Wilcoxon on per-series MASE, Friedman/Nemenyi across all five. Objective 1's "best model" = the best of ARIMA / Prophet / LSTM. The **served** model is that model unless it is significantly worse than the best benchmark; then the benchmark is served and the finding is reported.
**Why.** v1 selected on RMSE from one split without baselines, then lost to naive in production. MAPE is undefined near zero.
**Trade-off.** If a benchmark wins, the dissertation must say so plainly; the system's value then rests on decomposition and simulation, which is still a defensible contribution.

## D-07 — Engine 2's target is Engine 1's simulated shortfall probability
*2026-10-08 · approved by author*

**Decision.** For each synthetic profile with a proposed purchase, run the served Engine 1 with the proposed plan added and take P(balance < RM0 after any instalment due date within the horizon) as the target.
**Why.** v1's label was a hand-written formula the model simply re-learned (oracle F1 0.836, every model within 0.02), and the Engine 1 feature carried ≈1.5% of label variance. A simulation-derived label (a) has published precedent — Bijak, Thomas & Mues' dynamic affordability assessment; (b) mirrors BNM's financial-margin stress test; (c) matches the CCA 2025 affordability standard ("repay … without undue financial hardship over the duration"); (d) answers the supervisor's demand to justify how the label is assigned; and (e) makes the forecast genuinely load-bearing.
**Rejected.** Expert-rule labels and weak supervision (re-encode the author's opinion), transfer from public default datasets (wrong population, no schedule features — used only as a directional sanity check).
**Open.** Recommend the author shows this design to the supervisor / faculty consultants before P5 (PRD §8 Q7).

## D-08 — One synthetic population generator
*2026-10-08 · Claude decision*

**Decision.** `ml/datagen` generates transaction-level student histories from one cited parameter file (`ml/datagen/params.yaml`). Sources: Tan et al. 2026 and Osman et al. 2024 (demographics, income brackets), PTPTN 2026 rates (lump-sum disbursements), Tok & Cheah 2024 (monthly spend), DOSM HES 2022 (category shares), BNM / CCOB repayment statistics (~88% always on time, ~12% late-but-paid, < 0.5% unable to pay), provider fee schedules. The same generator produces the Engine 2 training profiles, the Engine 1 synthetic cohort and the three UAT persona CSVs.
**Why.** One set of assumptions to justify and document; the persona CSVs are statistically the same population the models learned from.
**Trade-off.** Parameters without a source are marked `assumed` in the file and listed in the dissertation's limitations.

## D-09 — One feature module, enforced by a schema hash
*2026-10-08 · Claude decision*

**Decision.** `backend/app/engines/risk/features.py` is the only place Engine 2 features are computed. `ml/engine2_train` imports it; it never re-implements a feature. Each artefact's `metadata.json` stores the ordered feature list and its hash; the server refuses to start on a mismatch.
**Why.** v1 trained `bnpl_income_ratio` as total debt/income and served it as monthly burden/income, and `forecasted_cash_flow` meant different things in training and serving.

## D-10 — Engine 2 training & selection protocol
*2026-10-08 · Claude decision*

**Decision.** Soft-label training by duplicate-and-weight; 5×5 repeated CV stratified by target decile and grouped by profile; Optuna tuning in an inner loop with the budget written to metadata; Brier primary, log-loss / ROC-AUC (p ≥ 0.30) / calibration slope / ECE secondary; Nadeau–Bengio corrected t-tests; calibration (none / Platt / isotonic) by nested CV; ablation without Engine-1 features; stress scenarios (income −20%, delayed PTPTN).
**Why.** Ports v1's proven harness and fixes its gaps (untuned defaults, single split, unreported tuning).

## D-11 — Repayment history is a flag, not a feature
*2026-10-08 · Claude decision*

**Decision.** Overdue instalments in the last 6 months are shown as a separate, rule-based flag citing BNM's suspension after 3 consecutive missed payments. They are not a model feature.
**Why.** The simulation label is about cash flow; a synthetic missed-payment variable would have to be wired into it by hand, recreating v1's distortion (synthetic users averaged ~3 misses, so "0 missed" dominated). Regulators require repayment history to be *checked*, which the flag does visibly.
**Trade-off.** The model score alone ignores repayment behaviour; the UI always shows both.

## D-15 — Hosting with a measured escape hatch
*2026-10-08 · supervisor plan + Claude fallback; step 1 triggered by the P0 spike*

**Decision.** Vercel (frontend), Render (backend), Supabase Singapore (DB). The P0 spike measured a process with the full stack including PyTorch at **607 MB RSS** (> Render's 512 MB); the served set without torch is ~300–470 MB. So step 1 of the escape hatch is **adopted now**: the backend runtime never imports torch; the global LSTM is trained offline (torch lives in the `ml` dependency group) and served via **ONNX Runtime**. If the real served stack (re-measured at the end of P4 and P6, then on Render in P8) still exceeds ~450 MB, move the backend to Google Cloud Run at 1 GiB.
**Why.** Render free is 512 MB / 0.1 CPU and sleeps after 15 minutes; torch alone adds ~170 MB.
**Trade-off.** Exporting the LSTM to ONNX adds a train→export→parity-check step (P3/P4) and a test that the ONNX output matches torch.

## D-19 — Running-ledger balance by default
*2026-10-08 · Claude decision*

**Decision.** Every transaction create/edit/delete and every instalment marked paid moves the balance; balance sync records a correction. The persona onboarding sets an opening balance.
**Why.** v1's manually synced balance went stale and its ledger mode was never switched on; Engine 1's simulation starts from this number.

## D-23 — Python version pinned by uv
*2026-10-08 · Claude decision; verified by the P0 spike (`reports/spikes/p0-dependency-spike.md`)*

**Decision.** Use `uv` with `.python-version` = **3.12**. The spike installed and imported the full stack on 3.12.15: FastAPI, supabase, statsforecast, prophet, torch (CPU index), onnxruntime, scikit-learn, xgboost, lightgbm, shap, optuna, scipy, statsmodels. `requires-python` is bounded to `>=3.12,<3.13`; torch is installed from the PyTorch CPU index with `--index-strategy unsafe-best-match`.
**Why.** The dev machine only has 3.14; 3.12 is the version every ML wheel supports (Windows verified; Render's Linux uses the same wheels). 3.14 was not tried because 3.12 worked first time.

## D-24 — Three named providers; everything else is manual "Other"
*2026-10-08 · author decision; revised same day after the author asked whether to include Grab and Boost (recommendation: exclude)*

**Decision.** The provider list is **SPayLater, TikTok PayLater, Atome and "Other provider (manual)"**.
- SPayLater, TikTok PayLater and Atome are rule-driven. Their rules come from real student users' checkouts: SPayLater and TikTok PayLater charge nothing at checkout and send the first bill one month after the purchase; Atome charges the first payment on the purchase date. The schedule auto-fills and the first date stays editable.
- "Other provider" applies **no rule and no fee formula**. The user types a provider name, the first payment date, the number of instalments and either the instalment amount or the total payable shown at their checkout. The app splits the total exactly in sen (leftover sen in the last instalment) and builds the schedule from exactly what was entered. The plan carries a small "schedule uses the dates and amounts you entered" note.
- Grab PayLater and Boost PayFlex are **not named** in the app. A provider becomes a named, rule-driven option only after a real checkout example is recorded in `refdocs/context/bnpl-billing-rules-my.md` and a test pins its schedule.

**Why.** The author has first-hand information only for these three. A guessed first due date creates phantom missed payments and moves instalments into the wrong weeks of the simulation, which is Engine 2's label (D-07). Naming a provider implies the app understands it, even with an "unverified" badge. Their fees also don't fit the single monthly-rate formula (research §C, medium confidence: Boost charges a flat RM5–10 fee plus 2.5% per month; Grab's interest varies by term), so a typed checkout amount is more accurate than any formula the app could apply.
**Rejected.** Listing Grab/Boost as "unverified" providers (the earlier version of this ADR: still implies support, and still needs a fee formula); encoding their rules from secondary web sources; hiding the "Other" option (students use other providers, and the stack view must include every plan they have).

## D-25 — Berka is a benchmark, not the population
*2026-10-08 · author approved its use*

**Decision.** The Berka / PKDD'99 Czech bank dataset is used only (a) as a real multi-account benchmark for comparing Engine 1's forecasters — its payment-type codes give ground truth for the fixed/variable split — and (b) as extra series for pre-training the global LSTM. It is never used to describe or represent the target users.
**Why.** PaySense targets Malaysian university students with a bank/debit account and e-wallets and usually no credit card. Berka is real, account-level, transaction-level data — rare and valuable for evaluating forecasting — but its account holders are Czech adults in the 1990s. The student population is represented by the cited synthetic generator (D-08).
**Trade-off.** Engine 1 results on Berka show how the methods behave on real household series, not on students; the dissertation reports them separately from the synthetic-student cohort.

## D-26 — Money stored as bigint sen; cross-user links blocked by composite foreign keys
*2026-10-08 · Claude decision (P0, migration 0001)*

**Decision.** Every money column is `bigint` integer sen (`amount_sen`, `current_balance_sen`, `total_price_sen`, `limit_sen`) — v1's `numeric(12,2)` is not carried over. Every table except `users` has `user_id`; every link between user-owned tables is a composite `(child_id, user_id) → parent (id, user_id)` foreign key (`unique (id, user_id)` on the parents), with `ON DELETE SET NULL (col)` (Postgres 15+) where a link is optional. Provider keys: `spaylater`, `tiktok_paylater`, `atome`, `other`, with a typed `provider_label` and a `schedule_source` of `provider_rule` or `manual` (D-24). `transactions.source` drops v1's `pdf` (out of scope).
**Why.** supabase-py returns `numeric` as a JSON float, which would reintroduce rounding in code that D-16 requires to be integer; storing sen keeps the whole stack integer from disk to engine. The composite keys make "a transaction pointing at someone else's plan" impossible at the database level, not just untested in the repository — defence in depth for hard constraint 4.
**Trade-off.** The API boundary must convert sen ↔ RM (decided in P1); hand-written SQL in the dashboard shows sen, not ringgit.

---

## Working assumptions (`ASSUMED:`)

Not decisions — guesses made to keep moving. Each one must be confirmed or killed before anything load-bearing is built on it. When one is resolved, delete it here and write a real ADR above.

1. `ASSUMED:` Berka is obtainable as CSV without a paid account (resolve in P3; fallback in PRD §8 Q3; usage scope fixed by D-25).
2. `ASSUMED:` 52-week horizon cap for risk checks (resolve in P4).
3. `ASSUMED:` ~10,000 synthetic profiles suffice (resolve in P5 with learning curves).
