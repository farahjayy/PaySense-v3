# WP16 + WP17-C1 — merge notes for the main session

> Written by the WP16 worktree session (branch `worktree-agent-aed2b6cc1205ddc0b`, from `af32943`). The worktree was told not to edit CHANGELOG, STATUS, DECISIONS, the PRD or questions.md; everything they need is below, ready to paste. Delete this file once merged.

## 1. CHANGELOG entry (paste under `[Unreleased]`, newest first)

```
### 2026-10-18 — WP16: savings buffer in both engines (D-50), band widening by history length (C2), bias-term sensitivity (C6); WP17-C1 honest limits
- **Changed:** *Settings:* migration `0005_savings_buffer.sql` (`user_settings.savings_buffer_sen bigint not null default 0`, ≥ 0); `db/user_settings.get_savings_buffer`/`set_savings_buffer`; new `api/settings.py` (`GET`/`PUT /api/settings`, PUT under `WRITE_QUOTA`, StrictInt sen 0..MAX, shared `settings_for`); router mounted as `settings_api`. *Engine 1:* `simulate` takes `starting_buffer_sen` (the cumulative margin starts from it; negative refused); `forecast_for`/`build_forecast` pass the user's buffer. The single 1.5 widening of the error record is replaced by a table by history length and series, `models/engine1/band_inflation.json` (new `engines/forecasting/bands.py`: parse, LF-normalised digest, refuse empty/unsorted/<1 factors); `prepare_ledger(recentre_errors=False)` keeps the switch for C6 analysis only. *Engine 2:* 17th feature `savings_buffer_to_income` (buffer ÷ expected monthly income, monotone −1), `DEFINITIONS_VERSION` v2, schema hash `10c5b74d0b8dfdbe`; template sentence for a small buffer; `MAX_ACTIVE` 17 (exact Shapley now 131,072 coalitions); `artefact.live_constants()` records the band-table digest, so an artefact built with another table is refused. *Generator:* `savings.*` in `params.yaml` (8 parameters, all `assumed: true`), `profile.savings_buffer_sen` on its own RNG stream (other fields unchanged). *ML:* labels version 3 (`--recentre-errors` for C6; manifest records the band digest); `train` records `serving_constants`; `export` accepts a parity row beyond 1e-3 only with a proven float32 threshold flip and never beyond 1e-2 (D-55); new `ml/engine1_eval/band_calibration.py` and `ml/engine2_train/compare_versions.py`. *Artefacts:* `models/engine2/v2/` (served; v1 kept), `models/engine1/band_inflation.json`. *Reports:* `reports/engine1/band_calibration.md`; `reports/engine2/` regenerated with `versions.md`, `tables/versions.csv`, `tables/bias_sensitivity.csv`, v1 kept in `reports/engine2/v1/`; `reports/datagen/` (131 parameters, 115 assumed). *Docs:* plan/execution `2026-10-18-wp16-engine-update`, `fintechathon-2026/honest-limits.md` (WP17-C1), `questions-wp16.md`, `wp16-self-audit.md`. Frontend: `schema.d.ts` regenerated only.
- **Decided:** D-54 (band widening by history length), D-55 (export parity: proven float32 flips), D-56 (serving keeps the user's error bias; re-centring is a sensitivity only); ASSUMED 39 (no P3 re-run: the cohort is byte-identical) and 40 (non-monotone band table).
- **Deviations:** the band table was planned to never shrink for shorter histories; forcing that made held-out income coverage 0.50 → 0.21, so each bucket takes its own best factor (ASSUMED 40, W3). The C6 script is `compare_versions.py`, not `bias_sensitivity.py`. ml-auditor run by hand (a fork cannot start subagents; W8). Engine 1 real-data serving check not re-run (MoneyData/Berka blocked by the network; W5).
- **Verified:** v1 reproduced on Linux first: `uv run python -m ml.datagen.export` and `uv run python -m ml.engine2_train.labels` into scratch → both SHA-256 equal the committed manifests. Then `uv run python -m ml.engine1_eval.band_calibration` → table spend 2.8/2.4/2.1/2.2, income 1.1/1.3/1.7/1.2 (from 17/26/39/52 weeks); `uv run python -m ml.datagen.export` → 10,000 profiles, `weekly_series.csv` byte-identical to v1; `uv run python -m ml.engine2_train.labels` → 10,000 labelled, 0 locked; same with `--recentre-errors` into `data/engine2/recentred/`; `uv run python -m ml.engine2_train.train --config full` → winner LightGBM, Platt, lockbox Brier 0.0142, 1 lockbox scoring logged; `uv run python -m ml.engine2_train.export` → parity 3,000 rows, 1 row over 1e-6 (0.00144, proven float32 flip on `limit_utilisation_with_purchase`); `uv run python -m ml.engine2_train.serving_check` → same band 92.0%, p95 0.45 s; `uv run python -m ml.engine2_train.stress` → identity Brier 0.0142, band agreement 0.918; `report`, `compare_versions`, `band_calibration` re-run into scratch → byte-identical; `serving_check` re-run into scratch after the last `features.py` edit → loads v2 (hash `10c5b74d0b8dfdbe` equals the running code), every accuracy figure identical, only timings differ (p95 0.34 s). `uv run pytest -q` → **2342 passed, 24 deselected (exit 0)**; `uv run ruff check .` and `ruff format --check .` → clean; `npm run gen:api` then `npm run check:api` and `npx tsc --noEmit` → clean.
- **Known issues / next steps:** apply migration 0005 (W1); band coverage stays below 80% for 17–25-week histories and for income below 52 weeks (W2); the lockbox was scored a second time for v2, disclosed (W7); run the real ml-auditor on the merged branch (W8); STATUS's 12.7% should read 11.9% (W9); re-find the demo scenario against the v2 model.
```

## 2. STATUS.md

Replace the end of the P6 row's text ("a change that reaches Safe exists for only 12.7% of non-Safe results (most are short before the purchase). Not done: bias-term sensitivity") with:

> a change that reaches Safe exists for only 11.9% of non-Safe results with v1 (most are short before the purchase); bias-term sensitivity done in WP16 (`reports/engine2/versions.md`).

(12.7% does not match the committed v1 serving check: `reports/engine2/v1/serving_check.json` gives 0.1190 of 126.)

Add (or tick) a WP16 row:

| Item | State |
|---|---|
| WP16 Engine update (C2, C5, C6) | ✅ Done in worktree, needs migration 0005 and the real ml-auditor — Engine 2 **v2** served (17 features, labels v3, LightGBM + Platt): lockbox Brier 0.0198 → **0.0142** (constant 0.1674), CV Brier 0.0163 → 0.0130, lockbox band agreement 91.5% → 91.8%; serving check on 200 fresh students: same band 95.0% → **92.0%**, change reaches Safe 11.9% → 12.6% (14 of 111), p95 0.50 s → 0.45 s. Engine 1 band coverage (held-out, 13-week total): spending 0.61 → 0.69, income 0.50 → 0.53; ~0.78–0.79 for spending from 26 weeks, 0.33–0.38 at 17–25 weeks. Bias sensitivity: re-centring the error record changes the label by −0.014 on average, same band 91.8%. |
| WP17-C1 Honest limits | ✅ Paragraph in `refdocs/fintechathon-2026/honest-limits.md`, every figure traced to a generated report |

Verification ledger line: `uv run pytest -q` → 2342 passed, 24 deselected (exit 0); ruff clean; `npm run check:api` + `npx tsc --noEmit` clean.

## 3. DECISIONS.md — new ADRs

```
## D-54 — The forecast band is widened by history length and series (C2)
*2026-10-18 · Claude decision during WP16 (replaces D-35's single 1.5 factor)*

**Decision.** The user's error record is widened by a factor read from `backend/models/engine1/band_inflation.json`, chosen by weeks of history (from 17, 26, 39, 52) and series (spend, income): spend 2.8 / 2.4 / 2.1 / 2.2, income 1.1 / 1.3 / 1.7 / 1.2. The table is fitted by `ml.engine1_eval.band_calibration` on 300 development students of the Engine 1 cohort (indices 4,000–9,999, not multiples of ten): per bucket, the smallest factor on a 1.0–6.0 grid whose P10–P90 holds the real 13-week total 80% of the time, else the factor with the best coverage. It is checked on the 60 held-out Engine 1 test students. The Engine 2 artefact records the table's digest and refuses a different table.

**Why.** With one factor of 1.5 the band held the real total 61% of the time for spending and 50% for income on held-out students, so P(shortfall) was more extreme than the evidence supports. With the table: 69% and 53%; about 78–79% for spending from 26 weeks of history and 79% for income from 52 weeks.

**Rejected / Trade-off.** A single larger factor (over-widens long histories). A factor that never shrinks for shorter histories (planned; forcing it made held-out income coverage 0.50 → 0.21, because weekly draws are clipped at zero and the simulated income is off-centre, so a wider band can hold the total less often — ASSUMED 40). Widening cannot reach 80% for 17–25-week histories (0.38 spending, 0.33 income) or for income below 52 weeks; a population error record or an income level correction would be needed and is left to the author (questions-wp16 W2). Synthetic students only; no real-data check of the table (W5).

## D-55 — Export parity accepts a row only when a float32 split flip is proven
*2026-10-18 · Claude decision during WP16 (amends D-40's 1e-3 parity gate)*

**Decision.** `ml.engine2_train.export` still requires ONNX and served predictions within 1e-3 of the trained model. A row beyond that passes only if walking the LightGBM trees shows a split that goes one way with the double threshold and the other with its float32 copy (which ONNX stores), and never beyond 1e-2. Each such row is recorded in `metadata.json` (`explained_by_float32_thresholds`), and the committed-model test enforces the same rule.

**Why.** The v2 export refused on one of 3,000 rows (0.00144): `limit_utilisation_with_purchase` = 0.9999924187 lies between LightGBM's threshold 0.9999924144 and its float32 copy 0.9999924302. That is the ONNX format, not a conversion bug.

**Rejected / Trade-off.** Raising the tolerance for every row (would hide a real conversion error). Snapping features to float32 at training (changes every label pairing for one boundary row). The served number can differ from the trained model by up to 0.01 on a row that sits exactly on a split.

## D-56 — Serving keeps the user's forecast bias; re-centring is a sensitivity analysis (C6)
*2026-10-18 · Claude decision during WP16*

**Decision.** Serving keeps centring the simulated paths on the user's own error record, including its mean (a level the model has been getting wrong is carried forward). `labels --recentre-errors` removes that mean for a second label run used only in `reports/engine2/versions.md`; nothing trains on it.

**Why.** Measured, not assumed: re-centring moves the label by −0.014 on average (mean absolute 0.043, 95th percentile 0.215) and keeps the same band for 91.8% of 10,000 students; irregular-income students move the other way (+0.035). The bias is small on average and has no consistent sign across personas, so removing it is not clearly better.

**Rejected / Trade-off.** Serving re-centred errors (would discard real evidence that the model is off for this user). The income median is about +35% of the recent level at the old factor (`band_calibration.md`) — widening does not move that, and neither does this decision.
```

Working assumptions (append to the list):

```
39. `ASSUMED:` (WP16 C6) "Re-run the Engine 1 evaluation on the corrected cohort" is satisfied without re-running P3: the regenerated `weekly_series.csv` is byte-identical to v1's (the savings buffer is a stock, not a weekly flow), so the MASE comparison would reproduce exactly; the new synthetic coverage is in `reports/engine1/band_calibration.md`.
40. `ASSUMED:` (D-54) The band table need not be monotone in history length; each bucket takes its own best factor on development students.
```

Amend D-50's trade-off line: the "v2 numbers" it mentions are the **v1 artefact** numbers in `reports/engine2/v1/` (the artefact versions are v1 → v2; the label versions are 2 → 3).

## 4. PRD

§7 Decision Log, one-liners:

| D-54 | The forecast band's error record is widened by a factor by history length and series (`band_inflation.json`, fitted on development students); the artefact records its digest | One factor of 1.5 held the real total 61% / 50% of the time instead of 80% (replaces D-35's factor) |
| D-55 | Export parity accepts a row beyond 1e-3 only with a proven float32 split flip, never beyond 1e-2 | ONNX keeps tree thresholds in float32 (amends D-40) |
| D-56 | Serving keeps the user's forecast bias; re-centring the error record is reported as a sensitivity only | Re-centring changes labels little and without a consistent sign |

Engine 2 feature table (after `instalment_to_income`'s block, last row):

| `savings_buffer_to_income` — savings buffer / expected monthly income (D-50) | User setting | ↓ |

Text that D-50 makes stale (amend):
- Engine 1 "Monthly margin" row: "Cumulative margin starts at RM0 …" → "Cumulative margin starts from the user's savings buffer (RM0 unless they enter one; D-50) …".
- Known limitation 11 (savings not credited): now resolved by D-50 for a student who enters a buffer.
- Glossary "Margin": "starts at RM0 today — savings are not assumed (D-27)" → "starts from the savings buffer the user enters, RM0 by default (D-50)".
- §7 row D-35 ("error paths with a 1.5x widening"): add "(widening replaced by D-54)".
- D-40's trade-off text quotes the 1e-3 refusal; add "(amended by D-55)".
- `data/synthetic/MANIFEST.json` also records Python 3.12.3 (was 3.12.15, the author's machine); the data files' digests are unchanged.

## 5. questions.md

Fold in W1–W9 from `refdocs/fintechathon-2026/questions-wp16.md`.

## 6. Things the main session must do

- **Run the real `ml-auditor`** on the merged branch (W8); the hand-run checklist is in `wp16-self-audit.md`.
- **Migration 0005** must be applied after 0003 and 0004 before `PUT /api/settings` works on the real database (W1). Add it to the migrations checklist and `check_rls.py` needs no change (no new table).
- **Re-find the demo scenario** against the v2 model: every Engine 2 number changed, and a student with a buffer now scores differently. Never fabricate it; if no scenario reaches Safe, say so.
- **Frontend:** no screen reads or writes the buffer yet. `GET`/`PUT /api/settings` is in `schema.d.ts`; a settings field is Lane C's work.
- **Assistant tools / recommendations:** they call `forecast_for` and the risk check, which already pass the buffer; nothing else needed.
- **STATUS 12.7% → 11.9%** (W9).
