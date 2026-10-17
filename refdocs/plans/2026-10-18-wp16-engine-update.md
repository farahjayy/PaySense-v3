# Plan — WP16 Engine update: savings buffer, band recalibration, bias-term sensitivity

> Execution: `refdocs/execution/2026-10-18-wp16-engine-update.md`. Scope: work-packages.md WP16 (change-list items C2, C5, C6) and WP17-C1 (the honest-limits paragraph). ADRs D-50, D-37, D-07, D-09, D-52.

## 1. Why this exists
- **C5:** a student with savings and a thin month is not at risk of missing an instalment, but v2's engines started every running margin at RM0 and called her At Risk (D-50).
- **C2:** the forecast band (P10–P90) covers the real outcome 46–69% of the time on the serving check instead of the nominal 80%, so P(shortfall) is more extreme than it should be.
- **C6:** P5 never measured how much the served forecaster's level bias moves the labels.
One retrain covers all three because each changes what the labels are made from.

## 2. What's already covered
The generator, the label pipeline (`ml/engine2_train/labels.py`), the D-37 training protocol (`train.py`: lockbox = every tenth profile, nested grouped CV, calibration, ablation), export to ONNX, the serving check, the stress tests and the report generator. The Engine 1 network itself does not change.

## 3. Scope
**In**
- **Savings buffer.** `user_settings.savings_buffer_sen` (migration 0005), `GET/PUT /api/settings`; Engine 1's cumulative margin starts from the buffer (dashboard forecast and risk check); Engine 2 feature `savings_buffer_to_income` (only in `features.py`, new schema hash); the generator gives each profile a buffer (assumed distribution, no cited Malaysian source).
- **Band recalibration.** The single widening factor (1.5) becomes a small table of factors by **history length** (and series kind), fitted on synthetic profiles that neither the LSTM nor the Engine 2 lockbox ever used, and checked on the 60 held-out Engine 1 test profiles. The table is a versioned file whose hash is recorded in the Engine 2 artefact (labels depend on it).
- **Bias-term sensitivity.** A second label run with every user's error record re-centred to mean zero; compared with the main run (label shift, band agreement).
- Regenerate labels, retrain Engine 2 under D-37 (the same lockbox scored once more, disclosed), export `models/engine2/v2/`, serving check, stress tests, regenerate `reports/engine1/serving_check.md` and `reports/engine2/` with v1 and v2 side by side; ml-auditor before training and before the reports.
- `honest-limits.md` (WP17-C1).

**Out, with reasons**
- MoneyData and Berka: their downloads are blocked by this environment's network policy (HTTP 403 / DNS), so the band check and any Engine 1 re-evaluation use the synthetic cohort only; the v1 real-data coverage rows are kept as the earlier version.
- Retraining the Engine 1 network (not in C2's scope: only the band rule changes).
- The settings field on a screen (the main session's WP3/WP7).

## 4. Approach
- Thread `savings_buffer_sen` (default 0) through `simulate` → `forecast_prepared` → `build_forecast` / `build_feature_inputs` → `run_check` / `assess` → `api/forecast.forecast_for` and `api/risk._evaluate`.
- Band rule: for each history bucket and kind, the smallest factor on a grid (1.0–6.0, step 0.1) whose development coverage reaches 0.80, or the factor with the best development coverage where none does; the factor never goes below 1. (Planned: "never decreases with shorter history". Dropped after the first fit showed that a wider band can hold the real total *less* often — weekly draws are clipped at zero, so widening raises the simulated total — and forcing it made the income band worse: 0.50 to 0.21 on held-out students.) Fitted by `ml/engine1_eval/band_calibration.py`, written to `backend/models/engine1/band_inflation.json` with provenance.
- Labels are D-07 as before (Engine 1's simulated shortfall with the plan), now with the buffer start and the new bands; `LABEL_VERSION` 3.

## 5. Risks & unknowns
| Risk | Confidence | Mitigation |
|---|---|---|
| Wider bands make more students At Risk before any purchase (labels shift up) | High | Reported old vs new; the buffer pulls the other way for students with savings |
| The full D-37 run is slow on 4 shared cores | Medium | Time the small config first; record any protocol change |
| Scoring the lockbox a second time | Certain | Disclosed in the report and the merge notes (v1 scored it once in P5) |
| The buffer distribution is invented | Certain | `assumed: true` with reason; stress test with buffer 0 |

## 6. Definition of done
The v2 artefact loads with the new hash and v1 is refused by the new code; the serving check passes; reports regenerate identically from their scripts; coverage before/after reported; old and new headline numbers side by side; full backend suite green; ruff clean; types regenerated.
