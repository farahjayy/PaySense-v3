# Execution — WP16 Engine update

> Companion plan: `refdocs/plans/2026-10-18-wp16-engine-update.md`.

## Before starting
Worktree branch from af32943; `cd backend && uv sync`. Reproduce v1 first: `ml.datagen.export` and `ml.engine2_train.labels` into scratch, compare with the committed manifests.

## Tasks
1. **Settings + buffer in Engine 1 (C5a).** Tests first (`tests/engines/test_simulate.py`, `tests/api/test_settings_api.py`, forecast/risk buffer tests). Migration 0005; `db/user_settings` getters/setters; `api/settings.py`; thread the buffer. Verify: tests pass.
2. **Engine 2 feature (C5b).** Tests first (`tests/engines/test_features.py`, templates). `savings_buffer_to_income`, `DEFINITIONS_VERSION` v2, template sentence. Verify: tests pass; v1 artefact refused.
3. **Generator buffer (C5c).** `params.yaml` `savings.*` (assumed), `profile.savings_buffer_sen` on its own stream; labels pass it. Verify: other profile fields unchanged (prefix and stream tests).
4. **Band rule (C2).** `ml/engine1_eval/band_calibration.py` fits the table on development profiles; `service.py` reads `models/engine1/band_inflation.json`; serving check reports v1 (1.5) and v2 coverage on the held-out profiles from 17 weeks of history. Verify: coverage table.
5. **Bias sensitivity (C6).** `labels.py --recentre-errors`; `ml/engine2_train/bias_sensitivity.py` compares two label files.
6. **Run.** Labels v3 (10,000) → ml-auditor → `train --config full` → export v2 → `serving_check` → `stress` → ml-auditor → `report`. Verify: artefact loads; report regenerates identically.
7. **Honest limits (WP17-C1)** from the regenerated reports.

## Wrap-up
Merge notes for CHANGELOG, STATUS, DECISIONS, PRD; questions-wp16.md; commit on the worktree branch.
