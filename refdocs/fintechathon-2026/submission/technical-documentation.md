# PaySense — technical documentation (draft for the submission)

> FinTechathon, Topic A. Every figure below is copied from a generated report and names it; re-copy after any re-run. The security design is summarised here and given in full in [`SECURITY.md`](../../../SECURITY.md).

## Context for readers outside Malaysia
Amounts are in Malaysian ringgit (RM; a ringgit is a hundred sen, and PaySense counts in sen). SPayLater (Shopee), TikTok PayLater and Atome are the buy-now-pay-later (BNPL) services students meet most at online checkouts; each splits a purchase into instalments, sometimes with a fee, up to a limit the provider sets. Many students' income arrives in lumps: PTPTN (the national higher-education loan fund) pays once a semester; allowances from family or a scholarship arrive monthly. Small instalments make a phone feel affordable today; several at once can outrun an income that arrives in lumps.

## 1. What PaySense does
A student signs in, brings in their history (file import, manual entry, or by pasting text to the assistant), and sees where their money is heading. Before a BNPL purchase they ask "can I afford it?" — in a form or in plain words to the assistant — and get Safe / Caution / At Risk, the reasons, and the smallest change that would make it Safe, or an honest "none does". Budgets, bill collisions, spending insights and ranked recommendations come from rules over their own data. Nothing changes until they press Confirm.

## 2. Architecture
Next.js frontend → FastAPI backend (the only process with database access, service key server-side) → Supabase Postgres (Singapore, row-level security on, no anonymous policies). The two engines run inside the backend from committed ONNX artefacts; training is offline (`backend/ml/`) and the backend never imports it. The assistant layer calls an LLM provider (Gemini now, Claude later, one interface) with the student's message and the figures the tools computed. Diagram: [`README.md`](../../../README.md#architecture).

## 3. Core algorithms

### 3.1 Financial health forecast (Engine 1)
- Known flows (confirmed recurring income and bills, BNPL instalments) are placed on their dates; only the variable part — weekly discretionary spending and unconfirmed income — is forecast.
- Candidates fixed by the literature review (ARIMA, Prophet, LSTM) were compared with benchmarks (naive, 4- and 13-week moving averages) on two public datasets and a synthetic student cohort, by rolling-origin evaluation and a pre-registered rule. **Served: a global LSTM** — geometric-mean MASE **0.8153** against **1.0438** for the best benchmark (13-week moving average); median per-series difference −0.1095, 95% CI [−0.1504, −0.0779], Holm-adjusted Wilcoxon p = 2.4e−37 over 242 series (`reports/engine1/README.md`).
- 1,000 simulated futures from the forecast and the student's own recent forecast errors (widened by a factor fitted by history length, D-54) give the running margin's 80% band, the chance of running short, and a health score. A savings buffer the student enters is the starting point (D-50); otherwise RM 0.

### 3.2 BNPL risk check (Engine 2)
- The provider's own rules build the exact schedule. The label for training is Engine 1's simulated shortfall probability with the plan added (D-07): 10,000 synthetic students, 17 money-only features defined in one file (`features.py`), never age, gender, ethnicity, nationality or employment.
- Candidates: random forest, XGBoost, LightGBM, with logistic regression and a constant as benchmarks; 5×5 cross-validation, tuning, calibration chosen on out-of-fold predictions, a lockbox of every tenth student scored once. **Served: LightGBM with Platt calibration** — lockbox Brier **0.0142** against 0.0200 for logistic regression and 0.1674 for the constant; Brier skill 0.915; band agreement 91.8% (`reports/engine2/versions.md`).
- Reasons are exact Shapley values from the model's own output; the counterfactual search tries fewer or more instalments, waiting, a lower price and another provider, and reports only a change the model itself rates Safe.

### 3.3 The assistant
- **Three tiers (D-48):** Tier 0 reads the student's data, Tier 1 computes or stores a *pending* proposal, Tier 2 writes — and Tier 2 is not a tool the model can call: it runs only from the confirm endpoint after the student presses Confirm on a card built from the stored proposal (digest, expiry, single-use claim).
- **No figure of its own (D-47):** every number in the model's answer must come from this turn's tool results, the server's step summaries or the student's own message (figures the model wrote into its own tool arguments do not count); otherwise the answer is replaced by the tools' summary.
- **Untrusted data:** transaction descriptions and pasted text reach the model as labelled data; an instruction inside them can at most lead to a proposal the student sees. Pasted rows must each match one line of the paste.
- **Caps:** six tool calls and a deadline per turn, per-user and global daily token budgets, a per-user request quota, one turn at a time. If the provider fails, guided mode keeps every tool usable without a model.
- **Measured:** live evaluation on gemini-3.1-flash-lite, 12 scenarios × 3 runs (one of them a four-turn conversation): **36 / 36** tasks completed, 0 guided fallbacks, 0 answers replaced by the number check (`reports/assistant/README.md`). An earlier run the same day scored 32 / 36: four turns hit the provider's HTTP 503 "high demand" and fell back to guided mode; one retry of a transient provider error inside the turn's deadline was added after it. The demo story was also run in a browser against the live model (`evidence/live-browser/`). The demo story run end to end through the API: 20 requests, 0 failed, plan, budget and paste confirmed, an injected instruction ignored (`evidence/demo-run/SUMMARY.md`).

## 4. Security design (summary)
Signed bearer tokens with revocation; a passphrase second factor (scrypt); every query scoped to the signed-in user in the repository layer and by composite foreign keys; RLS with no anonymous access; nonce CSP; body limits, rate limits, daily quotas and a ledger cap; artefact checks at start-up; money as integer sen; the assistant's tiers, confirm and number check; an audit log of every assistant step; consent, export and delete for the student's data. An independent review found no critical or high issues; its medium and low findings were fixed with tests or listed as known risks. Scans: 0 known vulnerabilities in the backend's dependencies and the frontend's production dependencies; 0 secrets in the git history (`evidence/scans/SUMMARY.md`). Full controls table, threat model and 15 known risks: [`SECURITY.md`](../../../SECURITY.md).

## 5. Honest limits
Use the paragraph in [`honest-limits.md`](../honest-limits.md) verbatim. Two more from this round: on the demo personas, no purchase in the demo grid reaches Safe without a savings buffer (`demo-scenario.md`), and the assistant's free-tier provider can be slow (p95 30 s in the latest evaluation).

## 6. Evidence index
| Claim | File |
|---|---|
| Engine 1 choice and statistics | `reports/engine1/README.md` |
| Band calibration | `reports/engine1/band_calibration.md` |
| Engine 2 v1 vs v2, lockbox, bias sensitivity | `reports/engine2/versions.md`, `reports/engine2/README.md`, `reports/engine2/lockbox_log.jsonl` |
| Assistant live evaluation | `reports/assistant/README.md`, `live_eval.json` |
| Demo story through the API | `evidence/demo-run/` |
| Demo purchases with and without a buffer | `refdocs/fintechathon-2026/demo-scenario.md`, `evidence/demo-scenario/` |
| Tests, coverage, build, browser journeys | `evidence/tests/SUMMARY.md` |
| Scans | `evidence/scans/SUMMARY.md` |
