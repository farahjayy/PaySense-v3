# Execution — P3 Engine 1 evaluation

> Plan: `refdocs/plans/2026-10-08-p3-engine1-evaluation.md`. Tasks run top to bottom. Each task carries its own **Verify** step; a task is not done until its Verify actually passes.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4).

## Before starting

- Read `CLAUDE.md`, `.claude/memory/preflight.md`, `refdocs/STATUS.md`, PRD §3.1 (Engine 1), §6 (P3), ADRs D-04, D-05, D-06, D-15, D-25, D-27, `refdocs/context/research-2026-10-08.md` section A, and `reports/datagen/README.md` (what the cohort can and cannot show).
- Everything lives under `backend/ml/engine1_eval/` and `backend/tests/ml/engine1/`. `app/` must never import `ml/`. Torch is allowed here (offline) and nowhere under `app/` (D-15).
- Candidate algorithms are fixed (D-05): Naive, moving average, AutoARIMA, Prophet, global LSTM. Do not add another without an ADR and the author's sign-off.
- **The selection rule is written down here before any result exists** and applied mechanically by the report script (D-06):
  1. Primary metric: pooled MASE across series at the 13-week horizon, on the real-data series and the synthetic cohort separately and combined.
  2. Let *L* be the literature candidate (ARIMA, Prophet or LSTM) with the lowest pooled MASE and *B* the best benchmark (naive or moving average).
  3. Serve *L* unless *B* beats *L* with a Holm-adjusted Wilcoxon p < 0.05 **and** a median per-series MASE difference of at least 0.02; in that case serve *B* and report that as the finding.
  4. Cost never changes the decision; it is reported (milliseconds per forecast, parameter count), because P4 may have to export the LSTM to ONNX if it wins (D-15).
  5. "Pooled" means: per model, the **geometric** mean of the per-series mean MASE at 13 weeks within each dataset, then the mean over datasets (equal weight per dataset). (Amended after a small run and before the full run: the arithmetic mean was dominated by one nearly-flat Berka account; ASSUMED 10.) The arithmetic mean is reported beside it. The synthetic cohort is scored at the longest history shown to the models; MoneyData and Berka with all history.
  6. *Clarification made after a small smoke run and before the full run:* an earlier draft of this list had a rule 4 that sent ties to the cheaper model. It contradicted rule 3 (D-06 serves the literature candidate unless it is significantly worse), so it was removed. The smoke run's winner did not influence the edit.
- Dates are never used to frame deadlines; "origins" below are forecast origins in the data.

---

### Task B1 — Dependencies and package skeleton
- **Files:** `backend/pyproject.toml` (`ml` group), `backend/ml/engine1_eval/__init__.py`, `backend/tests/ml/engine1/__init__.py`.
- **Steps:** add `statsforecast`, `prophet`, `torch` (CPU wheel), `scikit-learn` to the `ml` group, using the versions pinned by the P0 spike (`reports/spikes/p0-dependency-spike.md`); if `uv` hits the Windows `dist-info` lock, retry or `uv pip install` and record it. Extend `tests/ml/test_boundaries.py` so nothing under `app/` imports `torch`, `prophet` or `statsforecast`.
- **Verify:** `uv run python -c "import statsforecast, prophet, torch"`; `uv run pytest tests/ml/test_boundaries.py`.

### Task B2 — The common data frame and the loaders
- **Files:** `ml/engine1_eval/data.py`, `ml/engine1_eval/loaders/{synthetic,moneydata,berka}.py`, `data/external/README.md`, `data/external/{moneydata,berka}/download.py`, `tests/ml/engine1/test_data.py`.
- **Steps:** one tidy frame `series_id, week_start, value_sen, kind (spend|income), source` with complete Monday–Sunday weeks only and no gaps (a week with no transactions is an explicit zero). Loaders: the synthetic cohort (reads `weekly_series.csv`, with a profile-disjoint train/test split drawn from a seed), MoneyData (transactions → weekly spend and income, reserved transfers excluded the way `domain.flows.classify` would), Berka (accounts → weekly series per account; payment-type codes give the fixed/variable split). Download scripts print what they fetched and its checksum; raw files are gitignored. **If a download needs a login or payment, stop that dataset, write down why in the README, and continue** (PRD Q3 fallback). Tests use tiny hand-made fixtures that mimic each format.
- **Verify:** `uv run pytest tests/ml/engine1/test_data.py`; the synthetic loader on the real `data/synthetic/` returns 10,000 profiles × 2 kinds with no missing weeks.

### Task B3 — Metrics
- **Files:** `ml/engine1_eval/metrics.py`, `tests/ml/engine1/test_metrics.py`.
- **Steps:** MASE and RMSSE (scaled by the in-sample one-step naive error; undefined for a constant history, which is reported as skipped, not as zero), interval coverage and mean width, cumulative-margin MAE over a horizon (income forecast minus spend forecast, accumulated, against the realised). Hand-computed cases in the tests.
- **Verify:** `uv run pytest tests/ml/engine1/test_metrics.py`.

### Task B4 — Forecaster interface and the rolling-origin harness
- **Files:** `ml/engine1_eval/harness.py`, `ml/engine1_eval/forecaster.py`, `tests/ml/engine1/test_harness.py`.
- **Steps:** `Forecaster.fit(history)` then `.predict(horizon) -> point + residual-bootstrap quantiles`. Expanding window; minimum training length and horizon from the config (the product's real minimums: 17, 26 and 52 weeks of history are all evaluated); origins spaced by a fixed stride. The harness hands a candidate only `history[:origin]`. Tests: an **oracle** forecaster that is secretly given the future scores near-zero MASE (proving the harness measures what it claims); a candidate that tries to read past the origin raises; identical seeds give identical results.
- **Verify:** `uv run pytest tests/ml/engine1/test_harness.py`.

### Task B5 — Shared residual-bootstrap intervals
- **Files:** `ml/engine1_eval/intervals.py`, `tests/ml/engine1/test_intervals.py`.
- **Steps:** moving-block bootstrap (block = 4 weeks) of the candidate's own earlier rolling-origin errors, the same code for every candidate (PRD §3.1 "Uncertainty"); falls back to a plain residual bootstrap when fewer than two blocks exist and says so in the result.
- **Verify:** `uv run pytest tests/ml/engine1/test_intervals.py` — coverage of a well-specified simulated AR(1) lands near nominal.

### Task B6 — Benchmark candidates
- **Files:** `ml/engine1_eval/models/benchmarks.py`, `tests/ml/engine1/test_benchmarks.py`.
- **Steps:** naive (last value), moving average (window from the config, chosen on earlier origins only), and seasonal naive only if a dataset has a documented seasonality.
- **Verify:** `uv run pytest tests/ml/engine1/test_benchmarks.py`.

### Task B7 — AutoARIMA
- **Files:** `ml/engine1_eval/models/arima.py`, tests.
- **Steps:** `statsforecast.AutoARIMA` behind the interface; non-negativity applied after forecasting (spend and income cannot be negative); wall-clock recorded.
- **Verify:** unit test on a simulated AR(1); a smoke run on 20 cohort series.

### Task B8 — Prophet
- **Files:** `ml/engine1_eval/models/prophet_model.py`, tests.
- **Steps:** weekly data, yearly seasonality only when at least two years of history exist, holidays off (documented), no tuning on test origins; wall-clock recorded.
- **Verify:** unit test on a series with known weekly level shifts; a smoke run on 20 series.

### Task B9 — Global LSTM
- **Files:** `ml/engine1_eval/models/lstm.py`, tests.
- **Steps:** one model for all series of a kind, trained on windows from the training profiles only (never the profiles it is tested on), inputs scaled per series, fixed seed, early stopping on a validation origin, CPU. Export to ONNX is **not** done here; it is a P4 task if this model wins (record parameter count and inference time now).
- **Verify:** unit test that training twice with the same seed gives identical weights; a smoke run.

### Task B10 — Significance tests
- **Files:** `ml/engine1_eval/stats.py`, `tests/ml/engine1/test_stats.py`.
- **Steps:** Harvey–Leybourne–Newbold-corrected Diebold–Mariano, Wilcoxon signed-rank on per-series MASE, Friedman plus Nemenyi, Holm adjustment, bootstrap CI of the median MASE difference. Tests against textbook values.
- **Verify:** `uv run pytest tests/ml/engine1/test_stats.py`.

### Task B11 — Runner and stored results
- **Files:** `ml/engine1_eval/run.py`, `ml/engine1_eval/configs/{small,full}.yaml`, `tests/ml/engine1/test_run.py`.
- **Steps:** `python -m ml.engine1_eval.run --config small|full` writes one results table (one row per series × origin × model × horizon, plus the config and package versions) to `data/engine1/` (gitignored), streaming. The `small` config runs in minutes and is what the tests use.
- **Verify:** `uv run python -m ml.engine1_eval.run --config small` completes; a second run produces an identical table.

### Task B12 — Report, selection, ADR
- **Files:** `ml/engine1_eval/report.py`, `reports/engine1/` (generated), `tests/ml/engine1/test_report.py`, `refdocs/changelog/DECISIONS.md` (ADR D-32), PRD §7.
- **Steps:** read the stored table and produce: pooled-MASE table per dataset and horizon, by history length, coverage, cumulative-margin MAE, significance matrices, wall-clock and model-size table, figures. Apply the selection rule above mechanically and print which branch fired. README states datasets available and unavailable, the circularity caveat, and anything unflattering. Write ADR D-32 from the generated table.
- **Verify:** `uv run python -m ml.engine1_eval.report` regenerates `reports/engine1/`; a second run leaves `git diff` empty; `uv run pytest tests/ml/engine1/test_report.py` checks the benchmarks appear in every table and the rule's branch is stated.

### Task B13 — Audit
- **Steps:** run the `ml-auditor` agent on `ml/engine1_eval/` and `reports/engine1/` (leakage, protocol, honesty of the claims) and `python-reviewer` on the code; fix findings or list them in STATUS.

---

## What actually happened (deviations from the tasks above)

- **B2 datasets:** MoneyData downloaded from the Mendeley public API (checksum matches the one Mendeley publishes) and Berka downloaded from the CTU Relational Repository's public read-only guest MariaDB account (the original archive host did not resolve). Both obtained **without any login**, which resolves ASSUMED 3 for P3. The Berka script pages by primary key (the server cancels long statements), writes a `.part` file, checks the row count and a pinned SHA-256, and only then installs the file; a re-download reproduced the same checksums. `defusedxml`, `openpyxl` and `pymysql` joined the `ml` group.
- **B4 interface:** `Forecaster.forecast(history, horizon, start)` takes the week the history starts, because Prophet needs real dates. The harness gained `history_limit` (models see only the last N weeks; this is how the 17/26/52-week study is done) and `first_origin_date` (every model is tested only on origins at or after the LSTM's training cutoff, because the synthetic profiles share one calendar and a global model would otherwise be tested on weeks it trained on).
- **B5 intervals:** the shared interval is the per-step empirical quantile of the model's own earlier, already-observed errors, not the 4-week moving-block bootstrap. The block bootstrap exists to simulate whole paths, which is P4's job; for comparing marginal coverage the simpler method is the standard one. It needs eight earlier errors per step, which is why the synthetic test now uses stride 1.
- **B9 LSTM:** one network per kind (spend, income), L1 loss (it matches MASE), early stopping on held-out *profiles* (not a validation origin), 26-week input window.
- **Audit round (ml-auditor and python-reviewer on the code, before the full run).** Fixed: forecasts are stored and reused for the margin metric (nothing refitted); errors are scaled by the whole history so the history study shares a yardstick; a signed-bias column was added; a non-finite forecast is a failure; only expected failure types are recorded (a bug crashes the run) and the run exits non-zero if any model failed; the report keeps only series every model scored; Holm is applied over the literature candidates; Diebold-Mariano (HLN, Bartlett weights, overlap = ceil(horizon / stride)) is computed per series and reported; the rule is also applied at each history length; the Berka loader samples accounts before keeping their rows; the MoneyData loader verifies its checksum and closes the workbook; the LSTM no longer stops after one epoch when it has no validation windows.
- **Not changed, and why:** the primary metric stays pooled MASE because D-06 fixes it. The auditor's critical finding is real, though: weekly MASE rewards the median, which for monthly-paid income is zero, so an L1-trained LSTM can win MASE while being biased on the running total that Engine 2's label depends on (in the first small run it was best on MASE and near-worst on 13-week cumulative-margin error). The report therefore prints the margin rank and bias beside the decision. `ASSUMED:` 9 in DECISIONS records that margin error is a co-check, not a veto; the author may want to make it co-primary (that would amend D-06). The P4 residual bootstrap resamples the served model's signed errors, which re-centres paths, but P4 must measure the served model's level bias before Engine 2 trusts it.
- **Reported, not fixed:** the synthetic test series share one calendar and one half-year of origins, so significance over them is optimistic (stated in the report); torch determinism was checked on one machine only.

## Wrap-up (do not skip)

- [x] `refdocs/STATUS.md` — phase table, verification ledger
- [x] `refdocs/changelog/CHANGELOG.md` — session entry
- [x] `refdocs/changelog/DECISIONS.md` — ADR D-32 (winner) and any other decision; PRD §7 one-liners with the same ids
- [x] This doc updated to match what actually happened
- [x] Datasets that could not be obtained are named in the README and STATUS, with the reason
- [x] Next: write `refdocs/plans/<date>-p4-engine1-serving.md` + its execution doc
