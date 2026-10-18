# Engine evaluation: where the two engines are weak, and what to change

Scope note: a read-only evaluation of Engine 1 (financial health forecasting: global LSTM, residual-bootstrap Monte Carlo, band-widening table) and Engine 2 (BNPL risk classification: LightGBM with Platt calibration, trained on 10,000 synthetic students labelled by Engine 1's simulation). For each weakness and each fix it gives the expected benefit, the risk, the effort, whether a retrain is needed and whether the work can run in a cloud session. It ends with a ranked list. Nothing in the repository was edited, retrained or regenerated. This note is the only file written.

**Effort sizes:** S = one function plus its tests; M = a new module or artefact plus a generated report; L = several modules and regenerated artefacts.

**Evidence labels used throughout**

- **[report]**: measured, copied from a generated report (path given).
- **[here]**: measured in this pass by a throwaway script run against the committed artefacts and data (`data/synthetic`, `data/engine2`, `backend/models`). Every such run used development students or development rows only: no lockbox row, no held-out Engine 1 test student and no fresh-check student was read. These numbers are **exploratory**: one seed, one split, fixed hyperparameters, scripts not committed. Do not quote them in the README, deck or `honest-limits.md` until a committed `ml.` script reproduces them.
- **[inferred]**: reasoning or an extrapolation, not a measurement.

**Constraints that frame every option (CLAUDE.md, D-05, D-07, D-09).** Candidates are fixed: ARIMA, Prophet and LSTM for Engine 1; RF, XGBoost and LightGBM for Engine 2; SHAP-style explanations. Only benchmarks and configurations may be added without a new ADR and the author's sign-off. Engine 2 features exist only in `backend/app/engines/risk/features.py`, and any feature change is an ADR plus a retrain (PRD §3.2). Engine 2's label is Engine 1's simulated shortfall probability (D-07). No fabricated numbers. In the tables below, "D-05 status" says whether an option is a configuration or benchmark (an ADR is enough) or a new method (ADR plus the author's sign-off).

---

## 1. Engine 1: financial health forecasting

### 1.1 Weaknesses already in the reports

| # | Weakness | Numbers | Source |
|---|---|---|---|
| W1 | 80% band too narrow overall | Held-out P10–P90 coverage of the 13-week total: spending 0.69, income 0.53 (target 0.80). Fresh check: 0.72 and 0.53. | [report] `reports/engine1/band_calibration.md`, `band_fresh_check.md` |
| W2 | Short histories (17–25 weeks) far below nominal | Held-out: spending 0.38, income 0.33. Fresh: 0.42 and 0.31. Income is also low at 26–38 weeks (0.51/0.52) and 39–51 weeks (0.41/0.41); it reaches 0.79/0.78 only from 52 weeks. | [report] same files |
| W3 | Income median biased upwards | Simulated median minus actual, as a share of the recent level: income **+0.345**, spending +0.020 (held-out, at the v2 factor of 1.5). Re-centring the error record barely moves income (+0.321), so the error record's mean is not the cause. | [report] `band_calibration.md`, D-56 |
| W4 | Real-data calibration is v2-era only and poor | With ×1.5: Berka spend 0.60, Berka income 0.47, MoneyData spend 0.54, MoneyData income 0.46. Berka income bias +0.404. There is no v3 real-data check because the MoneyData and Berka downloads are blocked in the cloud. | [report] `reports/engine1/serving_check.md`, `questions.md` row 25 |
| W5 | LSTM under-forecasts the level | Mean signed error −0.27 naive-error units on synthetic spend and −0.94 on Berka spend. AutoARIMA beats it on 13-week synthetic cumulative-margin error (2.13 against 2.90). | [report] `reports/engine1/README.md`, D-34 |
| W6 | Recursion beyond 13 weeks never evaluated | ASSUMED 11. A 36-instalment label depends on about 150 weeks of recursive forecast. | [report] D-34, D-36 |
| W7 | P3 has no synthetic interval coverage | Each synthetic series has only 13 origins, so no step ever has 8 earlier errors. | [report] `reports/engine1/README.md` |

### 1.2 New findings from this pass

**N1. The per-week clip at zero is the main cause of the income bias, and part of the under-coverage. [here]**
`simulate.py` clips every simulated **week** at zero: `np.clip(point + draws, 0, None)`. Widening the error record pushes more weekly draws below zero. The clip deletes that negative mass and raises the simulated total. This is the mechanism behind ASSUMED 40, "a wider band holds the total less often".

Method: I rebuilt `records_for` from `ml/engine1_eval/band_calibration.py` on the 300 **development** students only, split them 150/150 by a seeded draw, and scored half B. The harness reproduces the report's development rows (spending 0.72, income 0.52 overall), which confirms it matches the served code.

| Variant (half B, 1,950 origins per kind) | Spending coverage | Spending median bias | Income coverage | Income median bias |
|---|---|---|---|---|
| Served (table, clip per week) | 0.72 | **+0.155** | 0.52 | **+0.285** |
| Same table, clip per month | 0.52 / 0.83 / 0.88 / 0.84 by bucket | ≈0 | 0.55 / 0.93 / 0.94 / 0.87 by bucket | ≈0 (−0.03 to +0.10) |
| Same table, clip the 13-week total only | 0.78 | −0.011 | 0.83 | +0.001 |

Buckets are 17–25 / 26–38 / 39–51 / 52+ weeks.

A side effect worth knowing: at the served v3 factors (2.1–2.8), the clip puts the **spending** median about 15% of the level too high. That makes margins pessimistic. The report's +0.020 spending bias was measured at the old factor of 1.5, so it hides this. [here]

**N2. The income band table and the income LSTM were fitted on a series that serving does not forecast for most users. [here]**
`data/synthetic/weekly_series.csv` (the Engine 1 cohort, used by P3, `export_served` and `band_calibration`) holds **all** income (`ml/datagen/export.py`, `weekly_series`). Serving and the Engine 2 labels forecast only income **not covered by a confirmed recurring item** (`series.build_weekly_series` with `confirmed_covered`; `labels.prepare` confirms every detected item).

On 200 development profiles regenerated in memory:
- the served (residual) income is a median **0%** of total income (mean 19%);
- zero weeks rise from 58% of total-income weeks to 81% of residual-income weeks.

So the +0.345 income bias and the income factors (1.1/1.3/1.7/1.2) describe allowance plus PTPTN plus wages. For long histories that money is placed as known flows, not forecast. This is a train/serve mismatch for the income network and for its band, and D-54 does not mention it.

**N3. Engine 2 never sees a short history, and the demo personas are short. [here], [inferred]**
- All 200 sampled Engine 2 profiles have **73–78 weeks** of usable history (`history.default_months: 18` in `params.yaml`). All 10,000 labels use the `paths` bootstrap (none uses `fallback`).
- The persona CSVs run from 01/08/2025 to 28/12/2025. That is about **21 complete weeks** [inferred from the CSV dates], which puts them in the worst band bucket (17–25 weeks: spend factor 2.8, held-out coverage 0.38 and 0.33).
- So the classifier is trained only in the ≥52-week regime and demonstrated in the 17–25-week regime: covariate shift on `disc_volatility`, the margin features and `income_p10_monthly`.

**N4. A PTPTN lump sum cannot be detected in a short ledger. [here]**
Detection needs at least 3 occurrences with gaps of 150–215 days (`recurring.py`), so at least about a year of history.
- In the 200-profile sample, 107 of 112 PTPTN holders had it detected (long histories).
- For the 5 who did not, PTPTN makes up a median of **100%** of their residual income series: the weekly LSTM is asked to forecast a semester lump from a 26-week window.
- The `frequent_bnpl` persona CSV holds one PTPTN row, so it can never be detected there.

**N5. The recursive continuation drifts low as the horizon grows. [here]**
Development students, origin at week 26. Figures are the median error of the cumulative total as a share of the level, at 13 / 26 / 39 / 52 weeks:

| Series | LSTM (recursive) | MA13 | Mean of LSTM and MA13 |
|---|---|---|---|
| Spending | −0.211 / −0.242 / −0.291 / **−0.338** | −0.023 / −0.049 / −0.035 / −0.047 | −0.113 / … / −0.184 |
| Income | −0.147 / … / **−0.224** | −0.056 / … / −0.034 | — |

Median absolute error at 52 weeks: LSTM 0.338 against MA13 0.165 for spending.

The error record is built from **8-week** paths (`errors.DEFAULT_HORIZON`), so the drift that grows with horizon is not in it [inferred]. That makes long-plan labels the least reliable ones, as D-36 already suspected, and now with a measured direction. It does not overturn D-34 (the LSTM still wins weekly MASE), but it shows that MASE and the running total disagree (ASSUMED 9).

**N6. The demo story is not an artefact of the clip. [here]**
I ran `scripts/find_demo_scenario.run_in_memory` (temporary directory only) with a scratch copy of `simulate` that clips per month:

| Persona and purchase | Simulated P(shortfall), served | Simulated P(shortfall), clip per month |
|---|---|---|
| frequent_bnpl, without the purchase | 1.000 | 0.653 |
| frequent_bnpl, with the RM600–799 phone | 1.000 | 1.000 |
| budget_conscious, without | 0.782 | 0.775 |
| irregular_income, with the phone | 0.511 | 0.555 |
| frequent_bnpl, with the phone and a RM1,000 buffer | 0.896 | 0.208 |

The purchases stay At Risk. The clip changes baselines and buffer cases, not the headline.

### 1.3 Fix options within the allowed candidates and configurations

In these tables, "Engine 2 relabel and retrain" means every Engine 2 label changes, so Engine 2 must be relabelled and retrained.

| ID | Fix | Expected benefit (evidence) | Risk | Effort | Retrain? | Cloud? | D-05 status |
|---|---|---|---|---|---|---|---|
| **F1** | **Clip per month, not per simulated week** (`simulate.py`: clip `income @ weights` and `spend @ weights`), then refit the band table under that rule | Half B with a refitted table: spending 0.77 / income 0.80 overall; from 26 weeks, spending 0.79–0.88 and income 0.84–0.87; median bias about 0 (from +0.155 / +0.285) [here]. Removes the cause of W3 and ASSUMED 40. | A single simulated week can be negative inside a month; this is a semantic change to explain. Still 0.58–0.59 at 17–25 weeks (needs factor about 5). | S | Engine 2 relabel and retrain | Yes | Configuration of the residual bootstrap. ADR amending D-35/D-54. |
| **F2** | **Population error-path record for short histories** (13-week ratio error paths pooled from development students, per kind × history bucket, scaled by the user's level; used below 26 weeks, or mixed with the user's own record by history length) | With F1, at 17–25 weeks: spending 0.86 (bias +0.03), income 0.82 (+0.02). Population-only for every bucket: spending 0.80, income 0.83 overall [here]. Closes W2. This is exactly the mechanism `questions.md` row 22 names. | Loses personalisation for short histories (only the level is the user's). The artefact must be digest-guarded like `band_inflation.json`. Synthetic-only fit. | M | Engine 2 relabel and retrain | Yes | Configuration. ADR plus author decision (row 22 asks for both). |
| **F3** | **Fit the income network and its band on the series serving forecasts** (residual income after detection, built from `profiles.jsonl` at each origin) | Removes N2's mismatch. Without it, every income coverage figure measures a quantity that is mostly placed, not forecast. | P3's MASE decision was made on total income, and the real datasets have no recurring split, so D-06 cannot be re-run like for like. Needs an ADR recording that. | M–L | Engine 1 retrain, then Engine 2 relabel and retrain | Synthetic parts yes; real-data D-06 re-check local | Configuration (same LSTM). ADR. |
| **F4** | **PTPTN-aware detection**: suggest a semester income from 1–2 occurrences when the text matches a known disbursement, the user confirms it, and it is placed as a known flow (no ML) | Takes lumps out of the LSTM's input for short ledgers (N4). Directly relevant to the personas. | A rule that leans on description text. Users must still confirm. | S–M | Engine 2 relabel (labels run detection) | Yes | Rule, not a model. ADR on the detection heuristic. |
| F5 | Level / quantile correction of the median per bucket (fitted on development students) | After F1 and F2 the remaining bias is ≤0.05 [here], so there is little left to gain. | Another fitted table; double-correction risk. | S | Relabel | Yes | Calibration configuration. ADR. |
| F6 | Split-conformal on the 13-week total | Half B coverage: spending 0.80, income 0.84, including 17–25 weeks (0.86 / 0.83) [here] | Produces **no paths**, so it cannot feed P(shortfall). D-04 rejected conformal intervals for exactly this reason. | S | No (as a check) | Yes | Use as an evaluation diagnostic. Serving it needs D-04 revisited. |
| **F7** | **Long horizon**: (i) evaluate recursion against MA13 out to 52 weeks and report it; (ii) use 13-week error paths (the LSTM's native horizon) instead of 8; (iii) beyond 13 weeks hold the forecast level, or use MA13 where it is significantly better at that horizon (the D-06 logic per horizon) | (i) Settles ASSUMED 11 with evidence (N5). (ii) and (iii) remove the downward drift of long plans. | (iii) changes served forecasts; it needs the D-06 test per horizon. | (i) S; (ii) and (iii) M | (i) no; (ii) and (iii) Engine 2 relabel and retrain | Yes (synthetic); real-data check local | Configuration and benchmark. ADR for (ii) and (iii). |
| F8 | Forecast combination (LSTM + MA13; ARIMA is too slow to serve at about 350 ms per fit × about 10 fits per request) | Halves cumulative bias at 52 weeks (−0.338 → −0.184 for spending) but has no better absolute error than MA13 alone [here] | "Ensembling" is not listed in D-05. D-06 must be re-run, including on real data. | M | Engine 1 and Engine 2 | Partly; real data local | Grey area: ADR plus author sign-off. **Low priority.** |
| F9 | Real-data band check of the v3 (or v4) bands on MoneyData and Berka | Restores the only evidence about real ledgers (W4) | None | S | No | **Local only** (downloads blocked) | — |

---

## 2. Engine 2: BNPL risk classification

### 2.1 Weaknesses

| # | Weakness | Numbers | Source |
|---|---|---|---|
| R1 | Labels saturated | 52.7% exactly 0 or 1 (38.4% at 0, 14.3% at 1). 58.6% within 0.02 of 0 or 1. | [report] `reports/engine2/README.md`, `versions.md` |
| R2 | Most students are short before buying | 46.0% have a baseline of 0.10 or more; 7.6% have exactly 1.0. Baseline P50 0.042, P75 0.575. | [report] README limitations |
| R3 | The purchase rarely decides the band | The band moves for 10.7%. The label changes by under 0.01 for 66.4%. | [report]; reproduced [here] |
| R4 | The label is mostly the baseline | Predicting label = p_without explains **71%** of label variance (Brier 0.0484 against 0.1680 for the constant). Mean added risk 0.080; 21.5% add at least 0.05. | [here] all 10,000 labels |
| R5 | Safe is unreachable by construction for most non-Safe results | 12.6% (14 of 111) reach Safe. 85.6% of the non-Safe results are already short before the purchase. With a shared seed the purchase can only add outflows, so p_with ≥ p_without on every path (0 of 10,000 labels has p_with < p_without). No purchase lever can bring a student with a baseline of 0.10 or more below 0.10 by simulation. At most about 16 of the 111 were reachable, and 14 were found (~88%). | [report] `serving_check.md`/`.json`; [here] monotonicity; [inferred] arithmetic |
| R6 | Shown number against simulation | Same band 92.0%; mean absolute gap 0.053; p95 0.193; max 0.473. | [report] `serving_check.md` |
| R7 | The model is weakest exactly where the purchase matters | CV, development rows: on the 957 profiles whose band the purchase moves, the current LightGBM puts 73.6% in the right band, against 91.3% overall. | [here] |
| R8 | The model cannot see purchase timing | The "wait for income" lever is judged by the simulation (7 of 14 suggestions). | [report] `serving_check.md`; `counterfactual._judged` |
| R9 | Zero income is out of distribution (ml-audit L2) | `savings_buffer_to_income` takes the cap of 10 when income is 0. More important: **no** training row has zero income. No other ratio is ever at its cap (the largest `instalment_to_income` is 4.34). Only 2 rows have the savings ratio at 10, and both are large buffers. A zero-income user puts every ratio at 10, a region the model never saw. | [here]; `questions.md` row 34 |
| R10 | Training histories are 73–78 weeks; personas are about 21 weeks | See N3. | [here] |
| R11 | The lockbox is worn | Scored for v1 and again for v2 (the same 1,000 students). | [report] `versions.md`, `questions.md` row 27 |
| R12 | Several levers look spent | Calibration: none / Platt / isotonic held-out Brier 0.0127 / 0.0126 / 0.0126. Learning curve flattens: 0.0131 at 4,320 profiles, 0.0126 at 7,200. Monotone constraints cost 0.0015 Brier (0.0114 free against 0.0128). 4 of 15 logistic signs disagree with the imposed directions (`disc_weekly_p90`, `disc_volatility`, `instalment_to_income`, `active_plans_with_purchase`). | [report] |

### 2.2 Is the model learning the right thing for a pre-purchase decision?

Only partly.

**What it learns.** The target is the absolute `p_with`. 71% of its variance is the student's position before the purchase (R4), and the Brier loss is dominated by profiles whose band the purchase cannot change. The model is therefore very good at reproducing the baseline and noticeably weaker on the decision-relevant cases (R7).

**What the explanations say.** Reasons are exact Shapley values against a Safe reference student (D-40). For an already-short student they mostly explain the starting position, not the purchase.

**What the counterfactual can do.** The counterfactual grid only changes the purchase, so for 85.6% of non-Safe results its "nothing reaches Safe" is a structural certainty, not a finding (R5).

**What the classifier adds.** Serving already runs the full simulation of every check (`check.run_check` computes `p_simulated` and `p_without`; p50 0.12 s). A judge may ask what the classifier adds. The honest answer is the reasons (Shapley values on a smooth surrogate) and the FYP's Objective 2, not accuracy.

The decision a student faces is "how much worse does **this** purchase make my position?". The engine can answer that exactly, because the with- and without-purchase simulations share a seed.

### 2.3 Options

| ID | Option | Expected benefit (evidence) | Risk | Effort | Retrain? | Cloud? | D-05 / ADR |
|---|---|---|---|---|---|---|---|
| **G1** | **Two-part output, "risk before" plus "added risk"** (see the note below this table) | Prototype (development rows, 5-fold, fixed parameters) [here]: Brier **0.0064** against 0.0127; band agreement 0.953 against 0.913; added-risk MAE 0.027 against 0.059; low-baseline Brier 0.0086 against 0.0092; band agreement where the purchase moves the band 0.757 against 0.736. **Most of the gain is the exact baseline, not better learning of the purchase effect.** That is still the right product shape: "you were at 45%; this phone adds 6 points" (cf. `ai_assistant_landscape.md`: the "from X% to Y%" gap). | Amends D-07/D-10 (training target). The shown p now carries the Monte Carlo noise of b (1,000 paths, small). Reasons explain q only; the UI must label both parts. | M | **Retrain only**: `labels.jsonl` already holds `label` and `p_without` for all 10,000 | Yes | Same family (LightGBM). ADR amending D-07, D-10, D-40, D-12. Author sign-off advised (changes how Objective 2 is framed). |
| G2 | Add `p_without` (simulated) as a feature | Brier 0.0072 [here]. The smallest change. | Reasons then say "your starting risk" as one big factor and do not separate the purchase. | S | Retrain only | Yes | Feature ADR (`features.py`, `Engine1Summary`) |
| **G3** | **Timing-aware plan feature** (e.g. the lowest P10 cumulative margin without the purchase at the month-ends where this plan's payments fall, and the checkout payment relative to it) | Lets the model see "buy after the allowance" (R8), so fewer suggestions fall back to simulation-only judgement | More features in a monotone model; must be pre-registered | S–M | **Relabel** (features are stored at label time; about 6 min [here]) and retrain | Yes | Feature ADR |
| **G4** | **Generator: a mix of history lengths** (for example 17–78 weeks), plus some near-zero-income and pre-detection-PTPTN students | Removes the covariate shift on the personas (N3, R9, R10). The highest value for demo credibility. | Adds assumed parameters (`params.yaml`, ASSUMED 8). Short-history labels inherit Engine 1's short-history weakness, so do F1 and F2 first. | M | Regenerate data, relabel, retrain | Yes | Generator ADR (D-31 family) |
| **G5** | **L2 fix**: savings measured against expected monthly **outgoings** (bills + BNPL monthly + 4.33 × `disc_weekly_p50`), which is defined when income is 0. Or set it to 0 when income is 0, with an explicit `income_known` flag. | Correct direction at zero income (R9). Removes a "RM10 buffer = strong protection" artefact. | Changes a feature definition (`DEFINITIONS_VERSION` bump) | S | Relabel and retrain | Yes | Feature ADR (`questions.md` row 34) |
| **G8** | **Counterfactual objective for already-short students**: the smallest change that keeps the **added** risk under a pre-registered threshold (e.g. Δ < 0.02 or q < 0.05), plus Engine 1 what-ifs on non-purchase levers (cut discretionary spend by X%, enter savings) | Among already-short students, 49.1% of purchases add under 0.01 and 69.6% add under 0.05 [here]. Most non-Safe students would get "this purchase adds little; your risk comes from X" instead of "no change reaches Safe". | The threshold must be fixed before results; wording must not read as "safe to buy" | S–M | No (judged by simulation, or by G1's q) | Yes | Amends D-41. No new algorithm. |
| G6 | Relax or drop monotone constraints on the 4 sign-disagreeing features | Up to 0.0015 Brier | Results-driven; weakens explainability | S | Retrain | Yes | **Skip.** Keep the pre-registered constraints. |
| G7 | Calibration changes | Nothing to gain (R12) | — | — | — | — | **Skip** |
| G9 | More profiles | The learning curve is flat beyond about 4,300 | — | — | — | — | **Skip** (re-check only if G4 widens the distribution) |

**How G1 works.** Keep the label from D-07 and rewrite it as `p_with = b + (1 − b)·q`:
- b = `p_without` from the simulation, which serving already computes;
- q = P(short with the plan | not short without it), exact under the shared seed.

The model is LightGBM with monotone constraints, trained on q with weight (1 − b). The served p is b_sim + (1 − b_sim)·q̂. Reasons are Shapley values of q, so they are about the purchase.

---

## 3. Should a new engine or model be added?

| Candidate | What it is | Value | D-05 status | Verdict |
|---|---|---|---|---|
| **(a) Marginal-impact engine** | G1 as a product surface: "before X% → with Y% (+Z points)". The before part comes from the simulation; Z is modelled (or simulated) and explained. | High, and the gap the landscape note found. No new ML family. | Configuration of the existing LightGBM and simulation. ADR amending D-07/D-40; author sign-off advised. | **Do** (with G1) |
| (b) Loan-stacking / multi-provider exposure model | Learn cross-provider stacking risk | Stacking is already exact in known flows (every unpaid instalment of every provider is placed). There is no real cross-provider outcome data, so a model would re-learn the generator. | It would be a new target or model, so ADR plus sign-off | **Skip as ML.** Present it as a deterministic exposure view (already on the dashboard) and as features already present (`dsr_with_purchase`, `bnpl_outstanding_to_income`, `active_plans_with_purchase`). |
| **(c) PTPTN- and income-aware purchase scheduler** | Search over the next N confirmed income dates × instalment counts the provider offers, judged by the Engine 1 simulation (as the wait lever already is), and return the earliest date and plan with the lowest added risk or the first Safe one | High demo value ("buy after 12 Nov allowance: Safe"). Uses only the simulation. The assistant (D-47) can propose it; the LLM produces no number. The current grid tries only next income + 1 day. | No new ML family. Extends D-41's grid: ADR. | **Do**, after G8 (it shares the search) |
| (d) Transaction categoriser model | ML text classifier for categories | Categories feed Engine 1's series. The only training data is the author's generator text, which is circular. An LLM categoriser would let a model indirectly move scores (against the spirit of D-47). | Using RF/XGB/LGBM for a new task, or an LLM: ADR plus sign-off | **Skip** (rules plus user edits, D-43, are adequate) |
| (e) Anomaly detection model | e.g. Isolation Forest on transactions | ASSUMED 23 already ships a robust MAD rule (WP14). Low marginal value. | A new family: ADR plus sign-off | **Skip** |
| (f) Outcome check (evaluation, not a served engine) | Cut each profile's ledger 26 weeks before its as-of day, simulate, and compare P(shortfall) with the **realised** synthetic margin of those 26 weeks (they exist in `profiles.jsonl`) | Turns "accuracy at copying the simulation" into a measured, if synthetic, calibration of P(shortfall) against outcomes, with benchmarks (constant; an Engine 1 that serves MA13) | Evaluation only; no ADR needed for the method | **Do** (see §4) |

---

## 4. Ranked recommendations

### 4.1 Run times (for planning compute, not a schedule)

| Job | Time | Basis |
|---|---|---|
| Label generation, 10,000 profiles | About **14 min** on the author's machine [report] (`CHANGELOG.md`, P5 labels entry). About **6 min** single-process here (34 ms per profile; 30 profiles reproduced their stored labels exactly) [here, extrapolated]. | |
| Engine 2 `train --config full` | **29 min**, `stress` 9 min [report] (`STATUS.md` P5 row, author's machine). Not timed here; expected the same order: sequential, n_jobs = 1 for the boosted models [inferred]. | |
| Engine 1 P3 `run --config full` | About **90 min**, mostly AutoARIMA and Prophet [report] | |
| Band calibration | The origin collection took 5 s for 7,800 origins; refitting a 41-point grid for 3 clip modes took 32 s. The whole script should take a few minutes [here / inferred]. | |
| Serving check | 200 students, p50 0.12 s per assessment: about a minute [report / inferred] | |
| Bundled v3 retrain | 11,000 labels (≈7 min) + train (≈30) + stress (≈9) + reports and serving check (a few): **under an hour of compute** [inferred] | |

### 4.2 Do now, in a cloud session

All data is synthetic and present locally. Every step below needs only `data/synthetic`, `data/engine2` and the committed artefacts.

1. **Outcome check (f)**: evaluation only, no retrain, M.
   - Cut each ledger at as-of − 26 weeks (plans' paid flags and detection as of the cut), run Engine 1 at 1,000 paths, and score P(shortfall) against the realised monthly margins of the cut-off weeks. Report reliability, Brier and band agreement.
   - Benchmarks: the constant, and an Engine 1 that serves MA13 (`serving.served_forecaster("ma13")`).
   - Use development profile indices only. Fix the subset before running.
   - About 1–2 min of compute for 2,000 profiles [inferred].
   - It upgrades the weakest sentence in `honest-limits.md` from a caveat to a measurement.
2. **F7(i)**: report the recursion beyond 13 weeks against MA13 and naive at 13, 26, 39 and 52 weeks, on development or fresh students. S, no retrain. This settles ASSUMED 11 with evidence.
3. **Draft the ADRs, then ask the author** (needs the author's sign-off): F1 + F2 (band), G1 + G8 (two-part output and counterfactual objective), G4 + G5 (generator and savings feature), G3 (timing feature).
4. **After sign-off, one bundled v3 build** (one relabel, one retrain, one fresh lockbox):
   1. Engine 1: F1 + F2, then F4 if accepted.
   2. Refit the band table on development students.
   3. Run the fresh check on a **new** group from the pool (indices 4,000–9,999, not multiples of ten, excluding the 300 development, 300 fresh-check and 60 test students).
   4. Generator G4, features G3 + G5.
   5. Labels for 11,000 profiles (indices 10,000–10,999 become the **new lockbox**; `profile_seed` is index-stable, so the first 10,000 keep their meaning).
   6. Train with the G1 target, stress, export, serving check, then re-run `find_demo_scenario`.
5. **(c) The scheduler**, on top of G8's search. No retrain. Judged by simulation.

### 4.3 Defer to the author's machine

- F9: real-data band and coverage check (MoneyData and Berka downloads are blocked here; `questions.md` row 25).
- The real-data part of D-06 if F3, F7(iii) or F8 changes the served forecaster.
- Anything that touches the real Supabase or the persona accounts (migrations 0003–0006, `questions.md` row 36).
- Windows parity of new artefacts (D-52).

### 4.4 Skip

(b) a stacking ML model; (d) an ML categoriser; (e) an ML anomaly detector; G6 relaxing constraints; G7 calibration; G9 more profiles; F5 unless F1 and F2 are rejected; F8 unless the author wants an ensemble chapter; serving ARIMA in any combination (cost).

### 4.5 Honest evaluation for each change

**Benchmarks in every table:**
- Engine 1 bands: the v2 (×1.5) and v3 (served table) bands beside the new one, plus MA13 run through the same bootstrap.
- Engine 2: the constant, the logistic regression, and a new **"no added risk" benchmark (predict p_without)**, which shows how much of any score is the baseline (Brier 0.0484 on all labels [here]).

**Fit, choose, check:**
- Engine 1: fit on development students; choose before looking; check once on a never-used fresh group.
- Engine 2: choose by 5×5 CV on development rows; score a **new** lockbox once and log it in `lockbox_log.jsonl`. Report the old lockbox only as continuity, disclosed as its third scoring.

**New subgroup rows:**
- Engine 2: band agreement where the purchase moves the band (the current model gets 73.6% in CV [here]); added-risk error; results by history length (17–25 / 26–51 / 52+ weeks), now that G4 makes short histories exist.
- Engine 1: coverage and bias by bucket and kind, including where 80% is still not reached.

**Must be re-reported** (old and new side by side, the D-50 precedent):
- `reports/engine1/band_calibration.md` and a new fresh check;
- `reports/engine2/README.md`, `versions.md` (add v3), `serving_check.md`;
- `refdocs/fintechathon-2026/demo-scenario.md`;
- **every number in `honest-limits.md`**;
- ADRs and PRD §7; `questions.md` rows 22 and 34 resolved; STATUS and CHANGELOG.

---

## 5. Points for the author (doc conflicts and gaps; not resolved here)

1. **The PRD's uncertainty row is stale.** PRD §3.1 says "moving-block bootstrap, block = 4 weeks". Serving resamples whole 8-week error paths (D-35, `simulate.path_bootstrap`; `BOOTSTRAP_BLOCK` applies only to flat records).
2. **D-04 against `questions.md` row 22.** D-04 rejects conformal intervals because they give no paths. Any conformal element (F6) needs D-04 revisited. F2's population error paths do give paths, so they do not conflict with D-04.
3. **D-54 does not say which income series the band table was fitted on.** It was fitted on total income (N2); serving widens residual income with it.
4. **The persona history length is not stated next to the band table.** The personas (about 21 weeks [inferred]) are in the 17–25-week bucket, where `honest-limits.md` already says coverage is 33–38%. The demo shows exactly that regime.
5. **Possible persona data issue** [inferred, not tested here]. `frequent_bnpl`'s baseline of 1.000 (every path short before any purchase) may partly reflect `questions.md` row 11: "SPayLater instalment" rows confirmed as monthly bills. Worth checking before the demo.

## Appendix: reproducing the [here] numbers

The scripts ran with `backend/.venv/bin/python` against the committed artefacts and lived in a session scratch folder (not committed). To make any of these numbers quotable, re-implement it as a committed `ml.` module with a generated report:

- **Label statistics (R4, R5, G8):** one pass over `data/engine2/labels.jsonl`.
- **Residual income (N2–N4):** `generate_dated_profile` → `labels.prepare` → `build_weekly_series` with and without `confirmed_covered`, on 200 non-lockbox indices (seed 7).
- **Band variants (N1, F1, F2, F6):** `band_calibration.records_for` logic on `dev_profiles()`, split 150/150 by `default_rng(123)`; population error paths and conformal quantiles fitted on half A and scored on half B; 300 draws.
- **Recursion (N5):** the same development students, origins at 17 and 26 weeks, 52-week horizon.
- **Two-part prototype (G1, G2, R7):** development rows only (`index % 10 != 0`), `KFold(5, shuffle, random_state=0)`, LightGBM with 300 trees, 15 leaves, learning rate 0.05, the repo's monotone directions, duplicate-and-weight soft labels.
- **Demo personas (N6):** `find_demo_scenario.run_in_memory` (temporary directory), with `service.simulate` swapped for a monthly-clip copy, run on the container's current date. The personas are shifted to end before the run date, so these figures differ a little from `demo-scenario.md`.
