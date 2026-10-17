# Execution — WP9 Execution evidence and demo script

> Companion plan: `refdocs/plans/2026-10-18-wp9-execution-evidence.md`.

## Tasks
1. `scripts/demo_run.py` + `tests/test_demo_run.py` (guided mode on the e2e app: every step 0–9, no 5xx, plans unchanged, audit rows exported, the buffer put back). Verify: pass.
2. Live: `cd backend && uv run python scripts/demo_run.py --in-memory` with the configured Gemini key. Verify: `evidence/demo-run/SUMMARY.md`.
3. `scripts/collect_test_evidence.py` + `tests/test_collect_test_evidence.py`. Full run at the end of the session writes `evidence/tests/`.
4. `refdocs/fintechathon-2026/demo-video-script.md`; `evidence/README.md`.

## Deviations
- The first live run's "Go ahead with that." re-ran the risk check instead of proposing, so nothing could be confirmed (and the number check replaced that narration). The script now sends one plain rephrasing in that case; the second live run proposed on the first try, so the rephrasing was not needed. The first run's files were overwritten by the second (the summaries are from the second run).
- `--render` rewrites the summary from the kept transcript (used once, to add the saved risk-check id column without another live run).

## Wrap-up
CHANGELOG, STATUS; commit and push.
