# Environment Setup — PaySense v3

> **Security:** never commit a real value from this file. `.env*` is gitignored; `.env.example` carries the *names* with blank values and is committed.
> Never paste a real token into a plan, an execution doc, a changelog entry, or a chat transcript. If one leaks, rotate it — don't just delete the message.
> **This repo is public.** A leaked key here is a leaked key on the internet.

Last updated: 2026-10-08

---

## Required variables

**One file for both apps: `.env` at the repo root** (template: `.env.example`). The backend reads it, then `backend/.env` if present (which wins); the frontend reads it from `next.config.ts`, and `frontend/.env.local` still wins.

**Backend** (read by `backend/app/core/settings.py`)

| Variable | Required | Where to get it | Read by | Notes |
|---|---|---|---|---|
| `DB_BACKEND` | `supabase` | `memory` for local development (D-71): an in-memory database with three demo students (`aina`, `hafiz`, `meiling`) already loaded; everything resets on restart. `supabase` in production | backend start-up | Never `memory` on a deployment: nothing is kept |
| `LOCAL_DEMO_PASSPHRASE` | `paysense-local-demo` | Any phrase of 12+ characters | memory mode only | The demo students' passphrase locally |
| `SUPABASE_URL` | When `DB_BACKEND=supabase` | https://supabase.com/dashboard → your project → Project Settings → API → Project URL | backend settings → db client | Create the project in region **Southeast Asia (Singapore)** |
| `SUPABASE_SERVICE_KEY` | When `DB_BACKEND=supabase` | Same page → API keys → the **secret / service_role** key | backend settings → db client | Server-side only. Never in the frontend, never in a `NEXT_PUBLIC_*` variable |
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
| `DAILY_WRITE_QUOTA` | `300` | Writes one user may make per Malaysian day across every write route (D-49, WP18) |
| `SMOKE_PASSPHRASE` | unset | Read only by `scripts/smoke_live.py`: the passphrase of the seeded tester it logs in as |
| `ASSISTANT_ENABLED` | `true` | `false` puts the assistant in guided mode (tools from buttons, no model) |
| `LLM_PROVIDER` | `groq` | `groq`, `gemini`, `anthropic` or `none` (D-53, D-70). No key for the chosen provider = guided mode |
| `GROQ_API_KEY` | unset → guided mode | https://console.groq.com/keys (free tier, rate limited). Server-side only. Default model `llama-3.3-70b-versatile`; change it with `ASSISTANT_MODEL` |
| `GEMINI_API_KEY` | unset → guided mode | Google AI Studio → Get API key. Server-side only (`SecretStr`), never logged or returned. Free-tier prompts may be used by Google to improve its products: synthetic personas only |
| `ANTHROPIC_API_KEY` | unset → guided mode | https://console.anthropic.com/settings/keys. Server-side only. Used when `LLM_PROVIDER=anthropic` |
| `ASSISTANT_MODEL` | `gemini-3.1-flash-lite` / `claude-sonnet-5-5` | Model name for the chosen provider; check it in the provider's console |
| `ASSISTANT_REDACT_DESCRIPTIONS` | `false` | `true` hides transaction descriptions from the model |
| `ASSISTANT_MAX_TOOL_CALLS` | `6` | Tool calls per turn before the turn stops |
| `ASSISTANT_MAX_OUTPUT_TOKENS` | `1024` | Output-token cap per model call |
| `ASSISTANT_TIMEOUT_SECONDS` | `30` | Deadline for one whole turn |
| `ASSISTANT_HISTORY_TURNS` | `8` | Earlier plain-text turns sent with a message |
| `ASSISTANT_USER_DAILY_TOKENS` | `200000` | Per-user daily token budget (Malaysian day) |
| `ASSISTANT_GLOBAL_DAILY_TOKENS` | `3000000` | Global daily cap across all users; switch a public URL on only with this set |
| `ASSISTANT_DAILY_REQUESTS` | `300` | Assistant chat and guided calls per user per Malaysian day (each writes audit rows); counted apart from `DAILY_WRITE_QUOTA` |
| `ASSISTANT_ACTION_TTL_MINUTES` | `10` | How long a proposal can be confirmed |
| `GOOGLE_CLIENT_ID` | unset → Google sign-in off | Google Cloud Console → APIs & Services → Credentials → OAuth client (Web application). Sign in with Google (D-69) is on only when this, `GOOGLE_CLIENT_SECRET` and `API_PUBLIC_URL` are all set |
| `GOOGLE_CLIENT_SECRET` | unset → Google sign-in off | Same OAuth client; shown once at creation. Server-side only (`SecretStr`) |
| `API_PUBLIC_URL` | unset → Google sign-in off | The API origin the browser uses, no trailing slash (`http://localhost:8000`; the Render URL in production). Register `API_PUBLIC_URL/api/auth/google/callback` as the client's redirect URI **exactly** (`localhost` ≠ `127.0.0.1`). `https://` also makes the sign-in flow cookie `Secure` |
| `APP_URL` | first `CORS_ORIGINS` entry | The frontend origin the API sends the browser back to after Google sign-in |
| `NEXT_PUBLIC_GOOGLE_SIGNIN` (frontend) | unset → no Google button | `true` shows "Continue with Google" on the login page. Build-time on Vercel. Set it only when the backend has the three Google variables |

---

## Setup

```bash
# from the repo root
pnpm install                                  # frontend packages, then `uv sync` for the backend
cp backend/.env.example backend/.env          # then fill in the values above
cp frontend/.env.example frontend/.env.local  # then set NEXT_PUBLIC_API_BASE_URL
pnpm dev                                      # API on :8000 and the app on :3000
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
