# Plan — P5 Engine 2 training

> Phase P5 of `refdocs/paysense-v2-PRD.md` §6. Execution doc: `refdocs/execution/2026-10-08-p5-engine2-training.md`.
> A plan says **what and why**. The execution doc says **how and in what order**.

## Why this exists

Engine 2 (BNPL risk classification) answers "how likely is this plan to leave the student short?" with a probability, a plain-language reason and a smallest change that would make it Safe. Its **label is not a formula the author wrote**: it is Engine 1's simulated probability that the cumulative margin goes below RM0 with the proposed plan added (D-07, D-33). The classifier therefore learns, quickly and explainably, what the simulation computes slowly; the proof that the forecast matters is an ablation, not an assertion.

The design is fixed in PRD §3.1 (decided design) and §3.2 (feature contract): soft labels by duplicate-and-weight, four candidates (Random Forest, XGBoost, LightGBM with **monotonic constraints**, and a logistic-regression benchmark), 5×5 repeated stratified CV grouped by profile, Optuna tuning in an inner loop, Brier score against the soft target as the primary metric, calibration chosen by nested CV, SHAP, pre-registered bands (Safe < 0.10, Caution < 0.30, At Risk ≥ 0.30), repayment history as a separate flag and not a feature (D-11).

## What P4 hands over (read the P4 audit notes first)

- `simulate` / `build_forecast` are the **only** way a label is produced. Training and serving call the same function.
- **Train/serve parity is the main risk** (the P4 ml-auditor's finding 10):
  - Serving uses the recurring items the user *confirmed*. The generator's `truth.recurring_truth` is an answer key and is forbidden as an input (D-31), so labels must be made by running **recurring detection on the profile's ledger up to the as-of date and confirming what it suggests** — otherwise training labels are cleaner than anything serving can see.
  - Plan paid status must be the status **on the as-of date** (`paid_dates` on or before it), not the end state.
  - The generator has no logging lag and no stale ledgers. P5 builds a stress set from the held-out profiles (a stale ledger, a missing month, income down 20%, the next PTPTN disbursement not arriving) and reports it separately. *Resolved 2026-10-09 (audit M5):* the first draft of this plan added such ledgers to the training set; the execution doc kept them apart, and they stay apart, because the stress test is a robustness evaluation and training on them would contaminate it.
- The label is the *served* model's simulation, so the training set is regenerated whenever the served model, `simulate`, the completeness rules or the generator parameters change (`params_hash` and a `label_version` are recorded in the artefact metadata).
- Level bias in the served forecaster (ASSUMED 9) matters here: the P4 serving report quantifies it, and P5 reports the sensitivity of the labels to removing the bias term.

## Scope

**In:**
- `backend/app/engines/risk/features.py` — the *only* place Engine 2 features are computed (D-09), with a `FEATURE_SCHEMA_HASH`. `ml/` imports it; nothing else re-implements a feature. Inputs are the ledger, plans, limits, a proposed plan and the Engine 1 outputs for the horizon.
- **Label generation** (`ml/engine2_train/labels.py`): for each synthetic profile, build the ledger as of its own `as_of` (drawn per profile across a full year, D-31 note), detect-and-confirm recurring items, run `simulate` without and with the proposed plan **to the plan's last instalment** (D-36), and store `p_shortfall_with`, `p_shortfall_without`, the Engine 1 summary features, the per-month shortfall definition (sensitivity only) and provenance. Streamed, seeded and resumable (`--resume` continues an interrupted file of the same settings, and refuses a file made with different ones).
- **Training** (`ml/engine2_train/train.py`): the four candidates, monotone constraints on the features whose direction is known (PRD table), Optuna inner tuning with the budget recorded, 5×5 repeated stratified CV (strata = quantile bins of the soft label, at most ten) **grouped by profile**, Brier primary (overall and where the baseline is under 0.10), log-loss / ROC-AUC at p ≥ 0.30 / calibration slope and ECE secondary, Nadeau–Bengio corrected resampled t-tests between candidates. Every tenth profile is a **lockbox** that no selection step sees (D-37).
- **Calibration** chosen by nested CV (none / Platt / isotonic) on single-repeat out-of-fold predictions of the development set, fitted on them and stored with the model.
- **Proof of the link:** ablation (retrain the winner without the Engine 1-derived features, both arms tuned inside every fold, ΔBrier with a t-based CI, overall and for the profiles whose baseline is under 0.10) and stress tests on the lockbox (income −20%, the next PTPTN disbursement not arriving, a stale ledger, a missing month, with an identity control).
- **Sensitivity runs:** the winner without monotone constraints, a learning curve (ASSUMED 3), and the per-month shortfall definition (ASSUMED 4). The bias-term sensitivity was not built and the report says so.
- **Artefacts** (`backend/models/engine2/<version>/`): the model file, `metadata.json` (training data version, feature list and hash, library versions, metrics, CV summary, calibration choice, git commit), and a start-up check that refuses to serve a mismatching feature hash.
- **Report** (`reports/engine2/`) generated by script: tables, figures, README with limitations; winner and calibration recorded as an ADR; bands confirmed as pre-registered, not tuned.

**Out (and why):**
- SHAP explanations, counterfactual search, the repayment flag and the risk endpoint (P6).
- Any algorithm outside D-05 (only benchmarks and configurations may be added).
- Real student data (D-14).

## Approach

1. `features.py` first, test-first, with hand-computed cases for every feature (including the limit-capped purchase and `limit_known = 0`), and a hash test.
2. The label pipeline on a handful of profiles, checked by hand against `simulate`; then a 1,000-profile dry run to measure cost and look at the label distribution (all-0 or all-1 labels would make the task trivial: the designed purchase ratios were chosen to avoid that, and this is where it is verified).
3. Training harness with the logistic benchmark first (cheapest, and the floor every tree model must beat), then the tree models with constraints.
4. Calibration, ablation and stress tests on the winner.
5. Export, hash check, report, ADR.

## Risks & unknowns

| Risk / unknown | Confidence | Mitigation |
|---|---|---|
| Labels are a deterministic function of inputs the classifier can see, so a good score proves little | High | The ablation and a held-out *profile* split are the evidence; the report says plainly that Engine 2 distils Engine 1 and what that does and does not show |
| Label distribution collapses to near 0 or near 1 | Medium | Checked on the dry run; purchase ratio range and persona mix can be revisited by ADR before the full run |
| Label generation is slow with a heavier served model | Medium | Measure on 200 profiles first; Engine 1 results are cached per profile; labels are written incrementally |
| Train/serve parity gaps (confirmed items, plan status, lag) | High | The three parity rules above, each with a test; the stress set; `label_version` in metadata |
| Monotone constraints hurt accuracy | Low | Reported as the price of monotonicity (literature: 0–3% AUC), with unconstrained variants as a sensitivity run |
| 10,000 profiles are too few for stable 5×5 CV | Medium | Learning curves (ASSUMED 5); the size can be raised by regenerating |
| The label is mostly the baseline (half of the first 10,000 students were already short before any purchase) | Realised | Report Brier for all profiles and for those whose baseline is under 0.10, and say how often the purchase moves the band |
| Long plans are truncated by a horizon cap, so the label understates their risk | Realised | D-36: the simulation runs to the last instalment; the report refuses truncated labels |
| Fairness: age and employment must not leak | Low | They are not generated as attributes and not features; the feature list is checked against a forbidden list in a test |

## Definition of done

- `cd backend && uv run pytest` passes, with `features.py` tested for every feature and the hash; no feature is computed anywhere else (a test searches `ml/` and `app/` for feature names outside `features.py`).
- A 10,000-profile label run completes, is reproducible from the manifest, and its label distribution is reported.
- The four candidates are compared under the grouped 5×5 CV with the stated metrics, the benchmark in every table; the winner and calibration are chosen by the rule written before the run and recorded as an ADR.
- The ablation shows the contribution of the Engine 1 features with a confidence interval, and the stress tests are reported even if unflattering.
- The artefact loads, the server refuses a feature-hash mismatch (tested), and `reports/engine2/` regenerates with an empty `git diff`.
- `ml-auditor` has reviewed the label pipeline for leakage and train/serve parity; findings fixed or listed in STATUS.
