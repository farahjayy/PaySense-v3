# Deployment — PaySense v3

> For the author. Nothing in the repository deploys itself: every step below is yours to run, and each one that costs money or makes something public says so. Variable names and where to get them are in `env_setup.md`; this file is the order of operations and the checks.

## What was and was not verified before you start

| Verified here | How |
|---|---|
| **The Docker image builds and runs** | `docker build` of `backend/Dockerfile` with two substitutions forced by this environment's network (the base image pulled from `mirror.gcr.io` because Docker Hub answered 429, and the local `uv` binary because `ghcr.io` blobs are blocked); every other line ran as written. The container started with the session's configuration, loaded both models (start-up refuses any artefact mismatch), answered `/api/health`, and idled at **82 MiB**; image 471 MB. Render pulls from Docker Hub and ghcr.io itself, so it uses the Dockerfile unchanged |
| The smoke script against that container | `smoke_live.py`: the service answers, CORS allows the origin, anonymous calls are refused; **login answers 503** because the real database does not yet have migration 0003's `passphrase_hash` column. Expected until the migrations are applied |
| The API runs with only its runtime dependencies | `uv sync --frozen --no-default-groups` (what the image runs); the backend test suite also passes without the ML group (`uv run --no-group ml pytest --ignore=tests/ml`) |
| The frontend builds for production and runs under the Content-Security-Policy | `pnpm build`; 26 Playwright journeys on desktop and phone with no policy violations, and no sideways scroll at 360 / 375 px |
| The assistant against the real provider | `scripts/assistant_eval.py --runs 3` (36 / 36), `scripts/demo_run.py --in-memory`, and the browser journey `pnpm exec playwright test -c playwright.live.config.ts`, all with the real Gemini key |

| **Not** verified — do these on deploy | Why |
|---|---|
| Migrations 0003–0006 on the real Supabase project | They cannot be applied from the build session (the author applies them); every v3 feature that stores something needs them |
| Anything v3 against the real database | Login itself needs 0003 |
| `FORWARDED_ALLOW_IPS` | Render's proxy addresses must be read from its documentation or observed (below) |
| A phone browser on the live URL | Needs the live URL |

## Order of operations

1. **Supabase** (the `paysense-v3` project, Singapore; 0001 and 0002 are applied). Apply **`backend/migrations/0003_login_hardening.sql`, `0004_budgets_assistant.sql`, `0005_savings_buffer.sql`, `0006_privacy.sql`**, in order, in the SQL editor, each from the branch head (0003 changed after it was first written). Then `cd backend && uv run python scripts/check_rls.py` (every table answers the anonymous key with 401) and `uv run pytest -m integration` (the `test_v3_migrations.py` tests stop skipping once the tables exist).
2. **Local `.env`** (the repo-root `.env`, from `.env.example`, with `DB_BACKEND=supabase`): `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SESSION_SECRET`, `CORS_ORIGINS`, and for the assistant `LLM_PROVIDER` and its key (`env_setup.md`).
3. **Demo and judge accounts**: start the API locally on the real database, then `cd backend && uv run python scripts/load_personas.py --api http://localhost:8000`. Usernames and generated passphrases go to the gitignored `data/private/persona_accounts.json`; deliver judges theirs privately. Check the demo against the real model and data: `uv run python scripts/find_demo_scenario.py --api http://localhost:8000` and `uv run python scripts/demo_run.py --api http://localhost:8000` (both write `evidence/`).
4. **Render** (the API). New → Blueprint → this repository; it reads `render.yaml` (service **`paysense-v3-api`**, so it cannot collide with the v2 service). Fill in the prompted values:
   - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` from step 1.
   - `GEMINI_API_KEY` (or `ANTHROPIC_API_KEY` with `LLM_PROVIDER=anthropic`). Left empty, the assistant runs in guided mode.
   - `CORS_ORIGINS`: a placeholder now, the Vercel URL after step 5.
   - `FORWARDED_ALLOW_IPS`: see "Proxy addresses" below.
   - `SESSION_SECRET` is generated for you; the token budgets, assistant cap and write quota have values in the blueprint.
   Deploys are manual (`autoDeploy: false`).
5. **Vercel** (the app). Import the repository, root directory `frontend` (keep "Include files outside the root directory" on: the pnpm lockfile and workspace file are at the repo root). Set `NEXT_PUBLIC_API_BASE_URL` to the Render URL **before** the first build (it is baked into the bundle). Deploy.
6. **Close the loop.** Set Render's `CORS_ORIGINS` to the Vercel URL (no trailing slash) and redeploy the API.
7. **Smoke test.** `SMOKE_PASSPHRASE=<that tester's passphrase> uv run python scripts/smoke_live.py --api https://<service>.onrender.com --origin https://<app>.vercel.app --username <a persona account>`. All seven lines must say PASS.
8. **The demo on the live URL**: `uv run python scripts/demo_run.py --api https://<service>.onrender.com` (writes `evidence/demo-run/`), then the checklist below on a phone.

## Proxy addresses

The login rate limiter keys on the connecting address. Behind Render's proxy that is the proxy unless uvicorn is told which proxies to trust, and trusting `*` would let anyone forge an address and dodge the limit. Set `FORWARDED_ALLOW_IPS` to the proxy range. Uvicorn accepts a comma-separated list that can include CIDR ranges. If Render's range is not documented where you look, check it empirically: with it unset, log in wrongly ten times from a phone on mobile data and from the laptop; if both get locked out together, the limiter is seeing one address (the proxy) and the range is needed. Record what you set in `env_setup.md`.

## Keep-alive and cold starts

Render's free web services stop after about fifteen minutes without traffic, and the next request waits for a cold start (tens of seconds, longer with a model to load). For a study with testers that is a bad first impression. The options, in order of preference:

1. **Pay for the smallest always-on plan for the weeks of testing** (spends money: your call). Nothing else to maintain.
2. **Ping `/api/health` every ten minutes** from a free monitor (UptimeRobot or cron-job.org). This keeps one free instance warm; it uses roughly 744 of the 750 free instance-hours in a month, so it fits only if this is the single free service on the account.
3. **Warm it by hand** ten minutes before each session by opening `/api/health` in a browser. Cheapest, easiest to forget.

## Live functional checklist (fresh browser session, then again on a phone)

Run it as one of the persona accounts, on the live URL, in a private window.

- [ ] The login page loads; a wrong passphrase shows one generic error and stays; the right one shows the privacy notice once, then the dashboard.
- [ ] Ask PaySense: the opening turn lists what needs attention; "Can I afford an RM799 phone on SPayLater over 3 months?" shows the risk card and the steps; "Go ahead" shows a confirm card, and nothing is saved until Confirm.
- [ ] Your data: enter a savings buffer, check the same purchase again, clear the buffer; download your data.
- [ ] The dashboard says the forecast is locked and why (no history yet).
- [ ] Import: choose a persona CSV (use `data/personas/budget_conscious.csv`; see "Persona dates" in `uat/README.md`), review, add. The count in the success message matches the preview.
- [ ] The dashboard now shows a score, a band, the chart and "Show the numbers". Reload: still signed in.
- [ ] Transactions: add one, edit it, delete it. A plan payment (once any exists) says it is managed in Plans.
- [ ] Recurring: confirm one suggestion; the forecast refreshes.
- [ ] Plans: add a plan from SPayLater with a price above the recorded limit: the preview shows the amount paid at checkout. Mark an instalment paid.
- [ ] About the model reads sensibly.
- [ ] Keyboard only: Tab reaches "Skip to content" first; the main journey works without a mouse.
- [ ] Log out, then press Back: the app does not show private data.
- [ ] Browser console: no red errors, no "Content Security Policy" lines.
- [ ] Phone: nothing scrolls sideways; the bottom bar shows five items; the import and the plan form are usable one-handed.
- [ ] **Memory:** Render → the service → Metrics → Memory stays under 400 MB through the checklist. If it does not, record the Cloud Run fallback as an ADR (D-15).

## Rollback and secrets

- Render keeps previous deploys: Deploys → a previous one → Rollback. Vercel: Deployments → Promote to Production.
- A leaked key is rotated, not deleted: Supabase → API → reset the service key, update Render, redeploy. Rotating `SESSION_SECRET` signs every tester out.
- Real participant answers live only under `uat/data/<run>/`, which is gitignored.

## Known limits to say out loud to testers

The first request after idle can be slow on the free plan; the assistant's free-tier provider can be slow or unavailable at busy times (it falls back to guided mode); only SPayLater, TikTok PayLater and Atome follow built-in rules. The full list is in `SECURITY.md` and the README's honest limits.
