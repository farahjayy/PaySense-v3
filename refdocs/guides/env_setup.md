# Environment Setup — PaySense v2

> **Security:** never commit a real value from this file. `.env*` is gitignored; `.env.example` carries the *names* with blank values and is committed.
> Never paste a real token into a plan, an execution doc, a changelog entry, or a chat transcript. If one leaks, rotate it — don't just delete the message.
> **This repo is public.** A leaked key here is a leaked key on the internet.

Last updated: 2026-10-08

---

## Required variables

**Backend — `backend/.env`** (template: `backend/.env.example`; read by `backend/app/core/settings.py`, created in P0)

| Variable | Required | Where to get it | Read by | Notes |
|---|---|---|---|---|
| `SUPABASE_URL` | Yes | https://supabase.com/dashboard → your project → Project Settings → API → Project URL | backend settings → db client | Create the project in region **Southeast Asia (Singapore)** |
| `SUPABASE_SERVICE_KEY` | Yes | Same page → API keys → the **secret / service_role** key | backend settings → db client | Server-side only. Never in the frontend, never in a `NEXT_PUBLIC_*` variable |
| `SESSION_SECRET` | Yes | Generate locally: `python -c "import secrets; print(secrets.token_urlsafe(48))"` | backend auth (HS256 signing) | Rotating it logs every tester out |
| `CORS_ORIGINS` | Yes | Your frontend origins, comma-separated: `http://localhost:3000` locally; add the Vercel URL in P8 | backend CORS middleware | No trailing slash |

**Frontend — `frontend/.env.local`** (template: `frontend/.env.example`, created in P0 Task 7 — `create-next-app` refuses a non-empty folder, so it can't exist before the scaffold)

| Variable | Required | Where to get it | Read by | Notes |
|---|---|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Yes | `http://localhost:8000` locally; the Render service URL in P8 | `frontend/lib/api` client | Public by design — it is inlined into the browser bundle |

## Optional variables

| Variable | Default if unset | What it changes |
|---|---|---|
| `SESSION_TTL_HOURS` | `12` | Login session length |
| `SUPABASE_ANON_KEY` | unset → `scripts/check_rls.py` refuses to run | The **anon/publishable** key (same API page as the URL). Used only by `scripts/check_rls.py` to prove it reads nothing; the app never needs it. Not read by `settings.py`. |
| `MODEL_DIR` | `backend/models` | Where served artefacts are loaded from |
| `MC_PATHS` | `1000` | Monte Carlo paths per simulation (lower only for local debugging) |
| `ANTHROPIC_API_KEY` | unset → template explanations only | Enables P10 LLM-phrased explanations. Get it at https://console.anthropic.com/settings/keys. Derived features only are ever sent (PDPA). |

---

## Setup

```bash
# backend (after P0 creates the uv project)
cd backend
cp .env.example .env          # then fill in the values above
uv sync
uv run uvicorn app.main:app --reload --port 8000

# frontend
cd frontend
cp .env.example .env.local    # then set NEXT_PUBLIC_API_BASE_URL
npm install
npm run dev
```

**Behind a proxy (Render, P8):** the login rate limiter keys on the TCP peer address, so start uvicorn with `--proxy-headers --forwarded-allow-ips=<the proxy's address>` — never `*` (a wildcard lets a client spoof `X-Forwarded-For` and dodge the limit) — and run a **single worker** (the limiter state is per-process). Without the flag every user shares the proxy's bucket and ten mistyped usernames lock everyone out.

**Python tooling note:** `httpx2` is a dev dependency because Starlette's `TestClient` requires it (the older `httpx` path is deprecated); it is not used by app code.

Build-time vs runtime: `NEXT_PUBLIC_API_BASE_URL` is baked in at **build time** on Vercel — changing it needs a redeploy. Every backend variable is **runtime** and lives in the Render dashboard in P8.

---

## Rules

- **Client-side bundles are public.** Anything inlined into a browser build is readable by anyone who opens devtools. A key that must stay secret goes through a server-side route, never into client code — no exceptions, no "it's just a prototype".
- **`.env.example` is the documentation.** Add the variable name there the moment you add the variable, or the next person's setup silently half-works.
- **A missing required variable should fail loudly at startup**, with a message naming the variable and pointing here. Silent fallbacks to a broken state cost hours.
- **Rotate on exposure, not on suspicion of exposure.** If you can't prove a key never left the machine, treat it as leaked.

## When a variable changes

Adding, renaming, or removing one means updating, in the same session: this file, `.env.example`, the deploy target's dashboard (if any), and a changelog entry. Miss one and the next environment breaks in a way that looks like a code bug.
