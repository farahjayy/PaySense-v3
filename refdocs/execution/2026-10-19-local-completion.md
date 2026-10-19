# Execution — Local completion round

> Companion plan: `refdocs/plans/2026-10-19-local-completion.md` (the pre-registered real-data rule lives there; this file is the order of work and the record of what was run).

## Tasks (each green and committed before the next)
0. **Baseline on Windows.** Pull the cloud work (`origin/main` at `c611f55`), branch `claude/local-dev`; run backend, frontend and Playwright; fix any platform gap. D-52: pin LF for the text artefacts the loaders digest, with a test.
E. **Real-data engine check (no account needed, so done while waiting on the author).** Download MoneyData and Berka; extend `ml.engine1_eval.serving_check` to score the served rule (R3) and the population record beside R2 and R1 on identical windows; run; regenerate `reports/engine1/serving_check.md`; apply the plan's rule 3.3.
H. **Env templates.** Variable names only, from `env_setup.md`.
A. **Database.** Migrations 0003 to 0006 (the author pastes them), `check_rls.py`, `pytest -m integration`; fix differences between the in-memory fake and the real service.
B. **Run the app on the real database;** walk every screen in a real browser.
C. **Real evidence:** `find_demo_scenario.py`, `demo_run.py`, `e2e_real_account.py`, the real-account Playwright run, `run_security_drill.py`.
D. **Live model:** `assistant_eval.py --runs 3`, the live browser journey; Anthropic if a key is given.
F. **ml-auditor** over the engine v3 round; fix FAILs; CONCERNs to `questions.md`; re-run `run_security_scans.py` and `collect_test_evidence.py`.
G. **Deploy** (Render, Vercel) and smoke test, `demo_run.py --api <live URL>`, phone checklist.
I. **Submission pack:** figures re-copied from regenerated reports.

## Run log (commands and wall times)
All on the author's Windows 11 machine, from `backend/` unless stated.

| Step | Command | Wall time | Result |
|---|---|---|---|
| Fast-forward | `git fetch`; `git merge --ff-only origin/main` | seconds | local `main` was at `ddb9123`, behind the cloud work; now `c611f55` |
| Backend deps | `uv sync --all-groups` | seconds | first run: `Access is denied` removing the project's `dist-info` (known, STATUS); second run succeeded |
| Frontend lint, types | `npm run lint`; `npx tsc --noEmit` | seconds | clean |
| Frontend unit tests | `npm run test` | 87 s | 48 files, **432 passed** |
| Frontend build | `npm run build` | under 2 min | builds |
| Backend suite | `.venv/Scripts/python.exe -m pytest -q` | 12 min 34 s | **2723 passed**, 25 deselected (integration, live) |
| Real-database tests, before any migration | `pytest -m integration -rs` | 82 s | 19 passed, 5 skipped ("apply migration 0003 / 0004 first"), 1 failed: the code reads `user_locks`, which does not exist until 0003 is applied. The project holds migrations 0001 and 0002 only |
| Playwright, first run | `npx playwright test` | 2.2 min | 22 passed, 6 failed, 2 skipped. All six were desktop tests waiting for the dashboard heading: the page was still "Loading" at the 5 s default because the single stub backend queues CPU-bound forecasts. Phone passed |
| Playwright, two workers | `npx playwright test --project=desktop --workers=2` | 46 s | 13 passed, 2 skipped (so not a product fault) |
| Playwright, default workers, again | `npx playwright test` | 1.2 min | 5 failed (same cause) |
| Playwright, after `expect.timeout` 15 s in `playwright.config.ts` | `npx playwright test` | 1.3 min | **28 passed**, 2 skipped |
| D-52 line endings | `pytest tests/engines/test_line_endings.py` | seconds | red first (9 of 10 failed: no `eol` attribute on the model JSON), green after `backend/models/**/*.json` and `*.yaml` pinned to LF in `.gitattributes`. The loaders already tolerate CRLF (`text_digest`, `population.digest`); the working tree here is CRLF because `core.autocrlf=true` |
| MoneyData, Berka downloads | `data/external/moneydata/download.py`; `data/external/berka/download.py` (first `trans` attempt lost its connection at 14 MB, the retry completed) | minutes | both checksum-verified, gitignored |
| Synthetic export regenerated (the gitignored `weekly_series.csv` was not on this machine) | `python -m ml.datagen.export --profiles 10000` | about 8 min | every file hash in the committed `MANIFEST.json` is identical to the cloud (Linux) run; only the recorded Python patch version differs (3.12.3 against 3.12.15). The 10,000-profile export reproduces across platforms. Manifest left as committed |
| Real-data check of the served band rule (task E) | `python -m ml.engine1_eval.serving_check` | about 6 min | section 3 added to `reports/engine1/serving_check.md`. Pre-registered rule: R3 not clearly worse than R2 (+0.18 coverage for 26 weeks or more, +0.23 for 17-25). Unflattering cells in questions.md row 45. Parity line (section 1) carried over because the stored evaluation results are not on this machine; synthetic income rows in section 2 differ slightly from the committed report (+0.073 to +0.095 bias, 0.68 to 0.67 inside), cause not isolated (the committed report predates the WP16 changes, and this is a different platform) |
| Engine tests | `pytest tests/ml/engine1 tests/engines -q`; `ruff check .`; `ruff format --check .` | 40 s | 585 passed; ruff clean |
| ml-audit C9 (start-up check of the population record) | `pytest tests/engines/test_artefact.py -k population` (red first: no `load_population` in the artefact module), then `pytest tests/engines tests/api -q` | 3 min 40 s | 902 passed; a tampered or unreadable population record now stops the risk model at load (`ArtefactError`), not at the first short-history request |
| Both engines load on this Windows tree | `uvicorn app.main:app --port 8000` (health 200); a script calling `served_forecaster()` and `load_if_present(MODEL_ROOT)` | seconds | band rule 3 (clip month, population below 26 weeks), Engine 1 `ServedLstm`, Engine 2 artefact v3 (`two_part`); working tree is CRLF (`w/crlf`), the digests tolerate it |
| ml-audit C4 (benchmark in the Engine 2 serving check) | red first (`test_serving_check_maths.py`), then `python -m ml.engine2_train.serving_check` (200 seeded students) | about 5 min | every committed statistic reproduced exactly on Windows (same band 95.5%, 16.0%, 76.5%); only timings differ (p50 0.26 s, p95 0.76 s here). New: benchmark "show the chance without the purchase" 91.0% same band, mean absolute gap 0.0722 against 0.0205 |
| Migrations 0003-0006 applied to `paysense-v3` (Supabase MCP `apply_migration`, one call per file, SQL verbatim) | list_projects (3 projects; `.env` checked, without printing it, to point at `paysense-v3`), list_tables, apply_migration x4, list_tables again | minutes | 0003, 0004, 0005 recorded in the migration history. 0006's call returned a history-key collision (three calls sent in parallel got the same timestamp) but its columns (`consent_version`, `consent_at`) exist on `user_settings`: the file's own `commit;` had already committed them. Only the history row for 0006 is missing; not re-run (it would fail on existing columns). Before: 9 tables, 3 users, 632 transactions (the earlier persona load); after: 13 tables |
| RLS check on the real project | `python scripts/check_rls.py` | seconds | 13 of 13 tables answer the anon key with HTTP 401, "anon key reads nothing". Supabase security advisor: only INFO "RLS enabled, no policy" (intended) and a WARN for `public.rls_auto_enable()` (SECURITY DEFINER, executable by anon/authenticated; not from our migrations; left untouched, to ask the author) |
| Real-database integration tests | `python -m pytest -m integration -q` | 34 s | first run 24 passed, 1 failed: `test_default_settings_row_has_no_balance_columns` still expected only two settings columns (stale since 0005/0006); fixed to the five real columns; **25 passed** |
