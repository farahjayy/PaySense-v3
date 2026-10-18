# Plan — Engine 1 outcome check and recursion check (evaluation only)

> Execution: `refdocs/execution/2026-10-18-engine-outcome-check.md`. Source: `refdocs/fintechathon-2026/research/research_notes/PaySense hackathon edge feature/engine_evaluation.md` §3 (f), §4.2 items 1 and 2 (F7 (i)), and its findings N5 and W6.

## 1. Why this exists
Every Engine 1 figure so far measures the forecast (MASE) or the band (P10–P90 coverage of a 13-week total). Nothing measures the number the product shows: **P(shortfall)**. Engine 2's labels are that number, so "the classifier copies the simulation well" is only as good as the simulation is at predicting what really happens. The evaluation note measured this in throwaway scripts; those numbers are not quotable until a committed `ml.` script reproduces them. Two jobs:

1. **Outcome check.** Cut each synthetic student's weekly ledger before its end, build exactly what serving builds at that cut, compute the served P(shortfall) for the next 13 weeks, and score it against what really happened in the held-back weeks.
2. **Recursion check.** The served LSTM is trained for 13 weeks and continued recursively beyond that (`onnx_model.py`); a long plan's label depends on that continuation (ASSUMED 11, D-36). Measure its cumulative-total error at 13, 26, 39 and 52 weeks against the naive and MA13 benchmarks.

Neither job fits, chooses or changes anything that is served. No ADR is needed (evaluation method only, note §3 (f)).

## 2. Scope
**In:** two `ml.engine1_eval` modules, their tests, two generated reports (`reports/engine1/outcome_check.md`, `reports/engine1/recursion_check.md`) and their CSV tables; a merge note for the changelog and STATUS.
**Out:** any change to `app/`, the served LSTM, the band table, Engine 2's labels or model; real data (MoneyData and Berka cannot be downloaded in the cloud); the full-profile version of the check (bills, BNPL plans and confirmed recurring items placed as known flows), recorded as a limit.

## 3. Students
Development students only: cohort indices 4,000–9,999 not divisible by ten (`LOCKBOX_EVERY`), so never Engine 2's lockbox and never the Engine 1 evaluation's train or test students (those are drawn from indices 0–3,999). Also excluded: the 300 fresh-check students (`band_fresh_check.fresh_profiles`) and the 300 students the served band table was fitted on (`band_calibration.dev_profiles`), so the served band is never scored on the students it was fitted on. A seeded draw of 2,000 from what is left (`outcome_check.outcome_profiles`); both jobs use the same students. A later fresh check must exclude them too.

## 4. Outcome check: method
- **Cuts:** 13 and, separately, 26 weeks before the end of each 78-week ledger. The 13 weeks after the cut are held back and are the outcome.
- **History length:** for each student and cut, one case per history bucket (17–25, 26–38, 39–51, 52+ weeks): a seeded length in each of the first three (a student who began logging that many weeks before the cut) and the whole history before the cut for 52+. The realised outcome does not depend on the history length, so the buckets compare like with like.
- **Served P(shortfall):** the steps of `service.prepare_ledger` and `forecast_prepared` at the cut: the user's error record (`service.error_record`), widened by the served table (`bands.inflation_for`), the served LSTM, `simulate.simulate` with 1,000 paths, a running margin from RM0 at the start of the cut's month plus the month-to-date net, short if below RM0 at ANY month-end inside the 13 weeks (`max_weeks = 13`). Known flows are zero (the weekly cohort holds only discretionary spending and all income). The month-to-date net is the cut month's share of the weekly totals, apportioned by days (serving reads it from dated rows). The seed is deterministic per case, shared by the LSTM and the MA13 runs.
- **Realised outcome:** the same `simulate` call on the realised held-back weeks with no error draws and one path, so the realised and simulated outcomes are defined by one piece of code.
- **Benchmarks, in every table:** a constant (the realised rate of the scored students at that cut: in-sample, the best any constant can do on them) and the same simulation driven by MA13 instead of the LSTM (its own error record, the served band table).
- **Scores:** Brier, Brier skill against the constant, log loss (P clipped to half a path, 1/2,000, from each end), AUC, expected calibration error over ten probability bins, a calibration table (P exactly 0, ten bins, P exactly 1: count, mean predicted, realised rate), the share at exactly 0 and exactly 1, confident misses (P = 0 and short, P = 1 and not short), band against realised outcome (Safe / Caution / At Risk), and a paired student-level bootstrap 95% interval for the Brier difference LSTM − MA13 and LSTM − constant. Each by cut, overall and by history bucket.

## 5. Recursion check: method
Origins at 17 and 26 weeks from the start of each ledger (52 weeks of future remain from week 26). The served LSTM's recursive forecast, naive and MA13 (`app.engines.forecasting.models`). Error at horizon h: (forecast total − realised total) / (recent level × h), recent level = mean of the last 26 weeks of history (all of it if shorter); a series with a recent level of 0 is left out and counted. Reported for spending and income separately: median signed error, MAE (mean absolute), median absolute error, and the share of series where the LSTM's absolute error is below MA13's.

## 6. Risks and limits (stated in the reports)
- Synthetic students only; every student shares one calendar (cohort weeks 2024-07-01 to 2025-12-28), so each cut tests one season.
- No known flows: the outcome is income minus discretionary spending. It tests the forecast-and-bootstrap part of P(shortfall), not bills or plans.
- Income is total income, not the residual income serving forecasts after confirmed recurring items (note N2).

## 7. Definition of done
Tests first (`tests/ml/engine1/test_outcome_check.py`, `test_recursion_check.py`; no LSTM); both scripts run for real; `uv run pytest tests/ml -q`, `uv run ruff check .` and `uv run ruff format --check .` green; reports carry "generated, do not edit"; merge notes in `refdocs/fintechathon-2026/outcome-check-merge-notes.md`.
