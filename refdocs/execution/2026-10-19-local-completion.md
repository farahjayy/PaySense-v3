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
