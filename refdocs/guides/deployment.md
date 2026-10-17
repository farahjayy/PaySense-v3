# Deployment — PaySense v3

> For the author. Nothing in the repository deploys itself: every step below is yours to run, and each one that costs money or makes something public says so. Variable names and where to get them are in `env_setup.md`; this file is the order of operations and the checks.

## What was and was not verified before you start

| Verified here | How |
|---|---|
| The API runs with only its runtime dependencies (no torch, pandas, scikit-learn) | A clean environment built with `uv sync --frozen --no-default-groups`; the app imports; every third-party import in `app/` resolves |
| Memory | The API in that environment: 100 MB idle, 112 MB after importing a persona and 30 forecasts; forecast p50 10 ms, p95 13 ms (warm). The Render free plan has 512 MB |
| The frontend builds for production and runs under the Content-Security-Policy | `next build` and `next start`; every script tag carries the request's nonce; 12 Playwright tests (desktop and phone) pass against that build with no policy violations |
| The smoke script | `backend/scripts/smoke_live.py`, tested against the real app on the in-memory database |

| **Not** verified — do these on first deploy | Why |
|---|---|
| The Docker image | The Docker daemon was not running where this was prepared, so `backend/Dockerfile` has never been built. If the Render build fails, the log will say which line; the Dockerfile is short |
| Anything against the real Supabase | No project existed; the migration has never been applied |
| `FORWARDED_ALLOW_IPS` | Render's proxy addresses must be read from its documentation or observed (below) |
| A phone browser on the live URL | Needs the live URL |

## Order of operations

1. **Supabase project** (free tier is fine). Region **Southeast Asia (Singapore)**. Note the project URL and the *secret / service_role* key (Project Settings → API). Never put that key anywhere public.
2. **Apply the migration.** Supabase → SQL Editor → paste `backend/migrations/0001_init.sql` → run. It has never been applied, so expect to read an error message at least once; send it over and it is a small fix. Then run `cd backend && uv run python scripts/check_rls.py` (needs `SUPABASE_ANON_KEY`) to confirm an anonymous client reads nothing.
3. **Local `.env`** (`backend/.env`, from `.env.example`): `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, a generated `SESSION_SECRET`, `CORS_ORIGINS=http://localhost:3000`. Run `cd backend && uv run pytest -m integration` once; these 20 tests hit the real database.
4. **Seed testers** (needs `backend/.env`): `uv run python scripts/seed_testers.py --roster ../uat/testers.csv`.
5. **Render** (the API). New → Blueprint → pick this repository; it reads `render.yaml`. Fill in the prompted values:
   - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` from step 1.
   - `CORS_ORIGINS`: leave a placeholder now and set it after step 6.
   - `FORWARDED_ALLOW_IPS`: see "Proxy addresses" below.
   - `SESSION_SECRET` is generated for you.
   Deploys are manual (`autoDeploy: false`). The first build installs about 120 MB of dependencies.
6. **Vercel** (the app). Import the repository, root directory `frontend`. Set `NEXT_PUBLIC_API_BASE_URL` to the Render URL **before** the first build (it is baked into the bundle; changing it later needs a redeploy). Deploy.
7. **Close the loop.** Set Render's `CORS_ORIGINS` to the Vercel URL (no trailing slash, no path) and redeploy the API. The CSP already allows the app to call only the origin in `NEXT_PUBLIC_API_BASE_URL`.
8. **Smoke test.** `cd backend && uv run python scripts/smoke_live.py --api https://<service>.onrender.com --origin https://<app>.vercel.app --username <a seeded tester>`. All seven lines must say PASS.

## Proxy addresses

The login rate limiter keys on the connecting address. Behind Render's proxy that is the proxy unless uvicorn is told which proxies to trust, and trusting `*` would let anyone forge an address and dodge the limit. Set `FORWARDED_ALLOW_IPS` to the proxy range. Uvicorn accepts a comma-separated list that can include CIDR ranges. If Render's range is not documented where you look, check it empirically: with it unset, log in wrongly ten times from a phone on mobile data and from the laptop; if both get locked out together, the limiter is seeing one address (the proxy) and the range is needed. Record what you set in `env_setup.md`.

## Keep-alive and cold starts

Render's free web services stop after about fifteen minutes without traffic, and the next request waits for a cold start (tens of seconds, longer with a model to load). For a study with testers that is a bad first impression. The options, in order of preference:

1. **Pay for the smallest always-on plan for the weeks of testing** (spends money: your call). Nothing else to maintain.
2. **Ping `/api/health` every ten minutes** from a free monitor (UptimeRobot or cron-job.org). This keeps one free instance warm; it uses roughly 744 of the 750 free instance-hours in a month, so it fits only if this is the single free service on the account.
3. **Warm it by hand** ten minutes before each session by opening `/api/health` in a browser. Cheapest, easiest to forget.

## Live functional checklist (fresh browser session, then again on a phone)

Run it as one of the seeded testers, on the live URL, in a private window.

- [ ] The login page loads; the wrong username shows an error and stays; the right one lands on the dashboard.
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

The first request after idle can be slow on the free plan; the app has no per-user write quota or ledger-size cap yet (fine for five to seven testers); only SPayLater, TikTok PayLater and Atome follow built-in rules.
