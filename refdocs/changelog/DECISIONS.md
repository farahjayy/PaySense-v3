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

**Decision.** Known flows (confirmed recurring income and bills, BNPL instalments, dated savings goals) are placed on their exact dates. Only weekly variable series are forecast — discretionary spend, and (D-27) income not covered by a confirmed recurring item. A residual-bootstrap Monte Carlo (1,000 paths) produces P10/P50/P90 margins and P(shortfall). Everything is anchored to today. *(D-27 replaced the original daily balance with a monthly margin and removed the starting balance; the original text said "daily resolution, day-of-week spreading" and P10/P50/P90 balances.)*
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

**Decision.** For each synthetic profile with a proposed purchase, run the served Engine 1 with the proposed plan added and take P(cumulative margin < RM0 at any month-end within the horizon) as the target. *(Originally "balance < RM0 after any instalment due date"; changed by D-27.)*
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

## D-19 — Running-ledger balance by default — **SUPERSEDED by D-27**
*2026-10-08 · Claude decision; superseded the same day when the author asked for a flow-based design. Kept for the record; do not implement.*

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

## D-27 — Engine 1 forecasts flows, not a balance
*2026-10-08 · author direction ("predict just by using the income and expenses prediction"); Claude specified the details. Supersedes D-19 and the balance anchor in D-04 / D-07 / D-21.*

**Decision.** There is no starting balance, no running ledger and no balance sync (`user_settings` no longer has balance columns). For each month of the horizon, each Monte Carlo path computes `margin = income − bills − BNPL instalments (incl. any checkout payment) − discretionary spend`. Confirmed recurring income, bills and instalments are *placed*; discretionary spend and any income not covered by a confirmed recurring item are *forecast* as weekly series by the same served model and residual bootstrap. Cumulative margin starts at RM0 today ("no savings assumed"). **Shortfall** = cumulative margin < RM0 at any month-end in the horizon; **P(shortfall)** is the share of paths where that happens, and it is Engine 2's label (D-07). The 4-month history gate stays (supervisor). Incomplete-looking months are warned about and kept (their noise widens the bands); they are never hidden behind a fake-precise number. The balance chart becomes a **margin chart** (monthly margin and cumulative margin bands, with and without the plan).
**Why.** Most tracking apps — and most students — have no reliable account balance, so a balance anchor (D-19) depended on the user logging every transaction; any gap silently corrupted every forecast and every Engine 2 label. BNM's own household stress test uses a *financial margin* (income − necessities − debt obligations), not a balance, so the flow definition is as citable as the balance one (research §B2). The author's three reference cases come out right without a balance: RM600 over 3 months is Safe on RM2,000 monthly income, At Risk on RM500 monthly income, and At Risk when living on RM2,000 savings with no income (the plan drains it).
**Consequences.** (1) Engine 2 features `min_balance_p10_without` and `balance_to_monthly_essentials` are replaced by margin- and income-based ones (PRD §3.2); `income_to_due_gap_days` is dropped because the label no longer depends on intra-month timing — timing is shown as a note. (2) P3 must evaluate the forecasters on a second series (weekly unconfirmed income) as well as discretionary spend. (3) The dashboard shows a month summary (income / expenses / net), not a balance. (4) Migration 0001 was edited before it was applied: the balance columns were removed.
**Trade-off / limitation.** Savings are not credited, so a student with real savings and no income looks At Risk; the UI says "this check assumes you pay from your monthly income, not savings". An optional "savings buffer" input is recorded as future work, not built. Intra-month timing (an instalment due days before the next income) is no longer part of the label.
**Rejected.** Keeping the running-ledger balance with stronger warnings (fragile to missing entries, the author's concern); an optional dated balance checkpoint with gap simulation (more machinery, and the author preferred flows); a hard completeness gate (testers with messy data would be stuck).

## D-28 — Provider limit caps the financed amount; the excess is paid at checkout
*2026-10-08 · author-described real checkout behaviour; details assumed (see ASSUMED 5)*

**Decision.** A provider's remaining limit = recorded limit − what is still unpaid on that provider's active plans. For a purchase of price P: `financed = min(P, remaining limit)`, `checkout payment = P − financed` (an immediate outflow in the purchase month, on top of Atome's first-instalment-at-checkout rule). Any monthly fee applies to the financed part only. If the provider carries a fee, the cap applies to the financed **total payable including the fee**, so the financed principal is the largest amount whose principal plus fee fits the remaining limit. No limit recorded = no cap, and the report says the limit was unknown. Engine 2 gets `upfront_to_income`, `limit_utilisation_with_purchase` and `limit_known` (PRD §3.2); the BNPL stack view shows total limit and utilisation across providers. Worked example from the author: limit RM200, price RM300 → RM100 at checkout, RM200 financed.
**Why.** Real providers do not let a purchase exceed the limit, they require the balance up front; ignoring that either rejects feasible purchases or understates the cash needed this month.
**Not modelled.** Using spare limit as a cash-flow buffer or credit-card substitute (strategic use of a large limit). That is a behavioural assumption the literature review does not support; the headroom is displayed and counted in utilisation only. Recorded as future work.
**Open.** Whether real providers cap on principal or on principal plus fee, and how they count used limit, is `ASSUMED:` until the author supplies a real SPayLater / TikTok / Atome example.

## D-29 — API money is integer sen; refunds/transfers are reserved categories; import is stateless
*2026-10-08 · Claude decision (P1 plan)*

**Decision.**
1. **Money over the wire is integer sen** (`*_sen` fields), never floating-point RM and never decimal strings. Request fields use a strict integer type, so `100.5`, `"100"` and `true` are rejected; a test fails if any OpenAPI property named `*_sen` is not an integer or any money-looking property is a float. D-16's "convert at the API boundary" is read as "convert at the *presentation* boundary": the frontend formats sen as `RM 1,234.56` and parses what a person types from the text (`parse_rm` / a `lib/money.ts` twin), so no float ever touches a ringgit amount.
2. **Refunds and own-account transfers use two reserved categories**, `Refund` and `Transfer` — no schema change. A refund is stored as income but never counts as income: it nets against spend in its month. A transfer is ignored in both directions. `domain/flows.classify` is the only place this is decided; Engine 1 (P4) imports it. `Transfer` keywords are limited to explicit own-account wording because a bare "transfer in" on a statement is usually an allowance.
3. **CSV import is stateless.** Preview returns rows; confirm receives the user's edited rows and re-validates them. Nothing is held server-side between the two calls. Rows that match already-stored transactions (same day, amount, direction, normalised description; multiplicity-aware) are flagged as duplicates and unchecked by default.
**Why.** v1 stored RM floats and converted at the edges; rounding bugs there are what the sen discipline exists to prevent. Refunds netting against spend keeps the discretionary series honest; counting them as income would inflate the income forecast. Render restarts and sleeps, so in-memory preview state would lose uploads.
**Rejected.** RM floats (v1); RM decimal strings (every client must parse them, no benefit over sen); negative transaction amounts (the `amount_sen > 0` invariant is load-bearing); a new transaction column for refunds (not needed yet); a server-side preview store.

## D-30 — A payment is tied to its instalment; ambiguous failures never delete a payment
*2026-10-08 · Claude decision after the P1 FastAPI review (HIGH finding)*

**Decision.** `transactions.bnpl_installment_id` links a logged payment to the instalment it settles, with a **partial unique index** (one payment per instalment) and a composite `(id, user_id)` foreign key. Logging a payment is therefore idempotent (`_ensure_payment` finds the existing row or inserts it). `mark_paid` logs first, then flips the instalment with a conditional update; if the flip errors it **re-reads the instalment** and treats a committed flip as success — it never deletes the payment on an ambiguous error. `create_plan` inserts instalments as unpaid, logs the checkout payments, and only then flips the checkout instalments to paid; on failure it deletes everything linked to the plan, each cleanup step independent so a failed step cannot mask the original error or skip the plan delete. `delete_many` sends ids in batches of 100.
**Why.** supabase-py has no transactions, and a client timeout looks identical whether or not Postgres committed. The first design ("on any error, delete the payment I logged") could erase a real payment after a committed-but-unacknowledged flip, leaving a paid instalment with no expense and no way to repair it (a retry says "already paid"). Tying the payment to the instalment makes the worst case recoverable (a logged payment against a still-unpaid instalment, fixed by one retry) instead of silent.
**Trade-off.** A transient inconsistency window remains (payment logged, instalment not yet flipped); both the forecast and the month summary would briefly count the cash as spent while the instalment still shows as due. **Rejected for now:** moving create-plan / mark-paid into Postgres functions via `supabase.rpc` for true transactions — the cleaner fix, but it moves business logic into SQL and splits it from the tested Python; revisit if the real-database tests show the window matters.

## D-31 — Synthetic population: what the generator may and may not show the models
*2026-10-08 · Claude decision after the P2 python and ML audits*

**Decision.**
1. **Answer keys are separated from inputs.** Each exported profile nests the persona, the generator's true income, the true provider limits and the recurring ground truth under `truth`; the Engine 1 cohort has no persona column. Training and serving code must never read `truth` (a P5 test enforces it); evaluation code may.
2. **The proposed purchase is built against the limit the student has *recorded*, not the true limit** (D-28: no recorded limit means no cap). Existing plans in the history are built against the true limit, because the provider really enforced it.
3. **Repayment behaviour is drawn once per student.** The cited 88 / 12 / <0.5% are shares of account holders (CCOB), so a student is "always on time", "sometimes late" or "misses one"; they are not per-instalment probabilities.
4. **The weekly series carries structure the forecasters are not told about** (AR(1) drift in the spending level, a payday-week lift, exam dips, outlier weeks). Day-of-week and payday-day effects only move spending within a week, so they are *not* claimed as weekly-scale difficulty.
5. **Every parameter is in `params.yaml`** with a citation or an `assumed` reason; structural constants that change outputs are parameters too. The report separates distribution matches from "wiring checks" that hold by construction.
**Why.** The first version leaked the true limit into the purchase (train/serve skew on `limit_known`), applied a holder-level statistic to instalments (only 37% of holders were fully on time against a cited 88%), and claimed weekly-scale richness it did not have, so a "forecaster beats benchmarks" result on it would have been partly an artefact. Each was found by the ml-auditor and fixed before any model saw the data.
**Trade-off.** More assumed parameters (105 of 121) and a noisier weekly total than the drawn one; the report says both. The synthetic population remains a stand-in, never evidence about real students.

---

## Working assumptions (`ASSUMED:`)

Not decisions — guesses made to keep moving. Each one must be confirmed or killed before anything load-bearing is built on it. When one is resolved, delete it here and write a real ADR above.

1. `ASSUMED:` Berka is obtainable as CSV without a paid account (resolve in P3; fallback in PRD §8 Q3; usage scope fixed by D-25).
2. `ASSUMED:` 52-week horizon cap for risk checks (resolve in P4).
3. `ASSUMED:` ~10,000 synthetic profiles suffice (resolve in P5 with learning curves).
4. `ASSUMED:` (D-27) Shortfall is judged on the cumulative margin from RM0, not on each month alone; P5 reports the per-month version as a sensitivity check.
5. `ASSUMED:` (D-28) The limit caps the financed total payable including fee, and used limit = sum of unpaid instalment amounts; confirm with a real checkout during P1.
6. `ASSUMED:` (D-27) Incomplete-month thresholds and the unconfirmed-income series follow the same candidates and protocol as discretionary spend (fix in P3/P4). P3 evaluates total weekly income; the confirmed/unconfirmed split is decided by recurring detection in P4.
7. `ASSUMED:` (D-31) The cited RM201-400 monthly spending band (Tok & Cheah 2024) is applied to *discretionary* spend only, with rent, phone and subscriptions added on top. The source most naturally describes total spending; the report states the interpretation.
8. `ASSUMED:` (D-31) 105 of 121 generator parameters are assumptions (listed with reasons in `reports/datagen/README.md`); they are chosen for plausibility and coverage and stress-tested in P5, not defended as estimates.
9. `ASSUMED:` (D-06, P3) The Engine 1 selection rule keeps pooled MASE as the primary metric, with 13-week cumulative-margin error and bias reported beside it as co-checks rather than a veto. The audit showed MASE can favour a model that is biased on the running total (it rewards forecasting the median). If the author wants margin error to be co-primary, D-06 must be amended before the served model is fixed in P4.
