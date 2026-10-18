# Handoff: what was done on cloud, what is left for local dev

> The cloud build session did every part of the competition scope that needs no local machine, no account of the author's and no change to the real database. This page lists what is left, **in the order to do it**, with the command for each step. Details of each step live in the linked guide; answers the author owes are in `questions.md`.

## A. What the cloud session could not do, and why

| Item | Why it needs local / the author | Where |
|---|---|---|
| Apply migrations 0003–0006 | The session may not change the real database's schema | `backend/migrations/README.md` |
| Every real-database check after them | Needs the migrations | step B2 |
| Deploy (Render, Vercel), `FORWARDED_ALLOW_IPS`, the provider key in Render | The author's accounts | `refdocs/guides/deployment.md` |
| `backend/.env.example` and `frontend/.env.example` | The session's permissions deny `.env*` files | `refdocs/guides/env_setup.md` lists every variable name to add |
| MoneyData / Berka downloads (real-data band check) | Blocked by the cloud network policy | `questions.md` row 25 |
| The Anthropic adapter against the real API | No credit yet | `questions.md` row 14 |
| The live-model browser journey on your machine (optional; already run on cloud 3 times) | Needs the provider key in your environment | `cd frontend && npx playwright test -c playwright.live.config.ts` |
| The `fyp-final` tag on the FYP repo | Another repository on the author's machine | row 1 |
| The slides, the video recording, the registration form | The author's | `submission/`, `demo-video-script.md` |
| Answers to the open questions | The author's decisions | `questions.md` |

## B. Local steps, in order

1. **Pull the branch** `claude/fervent-tesla-2rh1ov`; review and merge to `main` when satisfied (only the author merges). Prefer a **squash merge**: commit `d422555` added a production build folder (`frontend/.next-live/`, no credentials in it, checked) that the next commit removed; a squash keeps it out of `main`'s history.
2. **Apply the migrations** in the Supabase SQL editor (project `paysense-v3`), each from the branch head: `0003_login_hardening.sql` (it changed after it was first written: the `assistant_chat` lock name), `0004_budgets_assistant.sql`, `0005_savings_buffer.sql`, `0006_privacy.sql`.
3. **Check them:** `cd backend && uv run python scripts/check_rls.py` (needs `SUPABASE_ANON_KEY`; every table must answer 401), then `uv run pytest -m integration` (the `test_v3_migrations.py` tests stop skipping).
4. **Run the app on the real database:** `uv run uvicorn app.main:app --port 8000` and `cd frontend && npm run dev`; sign in once in a browser.
5. **Persona accounts** (they now need passphrases): `cd backend && uv run python scripts/load_personas.py --api http://localhost:8000` → `data/private/persona_accounts.json` (gitignored).
6. **Real-database evidence:** `uv run python scripts/find_demo_scenario.py --api http://localhost:8000`, `uv run python scripts/demo_run.py --api http://localhost:8000`, `uv run python scripts/e2e_real_account.py` and the real-account Playwright run (`npx playwright test -c playwright.real.config.ts`) as in WP1. Commit the regenerated `evidence/` and `demo-scenario.md`.
7. **Env templates:** add the variable names from `env_setup.md` to `backend/.env.example` (no values).
8. **Deploy** (`deployment.md`): Render blueprint (`paysense-v3-api`), Vercel, CORS, `FORWARDED_ALLOW_IPS`, the smoke test, `demo_run.py --api <live URL>`, the phone checklist, a keep-alive choice.
9. **Second-Opinion Check (D-57):** needs no migration (a saved report keeps it inside the existing jsonb `input`). On the real database, step 6's `find_demo_scenario.py` now also fills the *Adds* and *Safer timing* columns; pick the video's shot 10 from them. Answer questions.md 37 (the 5-point threshold and the RM1,500 wording) and 38 (the engine fixes the outcome check points to).
10. **Optional, real data:** download MoneyData and Berka and run `uv run python -m ml.engine1_eval.serving_check` for real-data band coverage.
11. **Before submitting:** re-run `scripts/run_security_scans.py`, `scripts/run_security_drill.py` and `scripts/collect_test_evidence.py`; re-copy the figures in `submission/` from the reports they name; record the video with `demo-video-script.md`.

## C. Checks that run without you

Every push runs `.github/workflows/ci.yml` (green on the branch at the end of the cloud session): backend lint and the full test suite (incl. the ML tests), the backend tests without the ML stack, the frontend lint, types, API contract, unit tests and build, the browser journeys on desktop and phone, and a secret scan of the whole history. None of it calls the model provider or the real database.
