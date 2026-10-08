# PaySense v2

An AI-driven decision support system that helps Malaysian university students make informed Buy Now, Pay Later (BNPL) purchasing decisions — by forecasting their financial health and classifying the risk of a proposed BNPL purchase before they commit.

**Status:** scaffolded 2026-10-08 — no application code yet. See [`refdocs/STATUS.md`](refdocs/STATUS.md).

Final Year Project, BSc (Hons) Computer Science, Universiti Teknologi PETRONAS — Nur Farah Binti Ahmad Nazri. Supervisor: Dr. Nazleeni Samiha Bt Haron.

## What it does

- **Financial health forecasting.** Places the student's known income, bills and BNPL instalments on their exact dates, forecasts only their discretionary spending, and simulates 1,000 possible futures to show the projected balance with a P10–P90 band and the probability of running short on any due date.
- **BNPL risk classification.** Before a purchase, scores the probability that the student will not be able to pay an instalment in full — Safe / Caution / At Risk — using a calibrated classifier trained on simulated shortfall outcomes for a synthetic population of Malaysian students.
- **Explanations.** The top reasons behind every score (SHAP) and the smallest change that would make the purchase Safe — fewer instalments, waiting until after the next allowance, a lower price, another provider.
- **BNPL across providers.** SPayLater, TikTok PayLater, Atome and any other provider (entered manually) in one place, with provider-accurate schedules for the three named providers, the total monthly commitment, a due-date timeline and reminders.
- **Ledger.** Manual entry and CSV import with preview, recurring income and bills, a running balance.

## Requirements

- Python (version pinned in `backend/.python-version` during P0) managed by [uv](https://docs.astral.sh/uv/)
- Node.js 20+ (developed on 24)
- A Supabase project (free tier, Singapore region)

## Setup

```bash
git clone <this repo>
cd backend
cp .env.example .env      # fill in — see refdocs/guides/env_setup.md
uv sync
cd ../frontend
cp .env.example .env.local
npm install
```

Apply the SQL files in `backend/migrations/` to your Supabase project in order, then seed a user:

```bash
cd backend
uv run python scripts/seed_users.py --username demo --display "Demo" --persona budget_conscious
```

## Usage

```bash
# terminal 1
cd backend && uv run uvicorn app.main:app --reload --port 8000
# terminal 2
cd frontend && npm run dev   # http://localhost:3000 → log in with the seeded username
```

(The backend and frontend commands above exist as of P0. The backend needs `backend/.env` for anything that touches the database; see `refdocs/guides/env_setup.md`.)

## Project layout

Entries marked *(planned)* do not exist yet and arrive with their phase; everything else is built (P0).

```
PaySense_v2/
├── backend/
│   ├── app/
│   │   ├── api/            auth, health, deps, rate limiter, response schemas; (planned) transactions, imports, recurring, plans, forecast, risk, dashboard
│   │   ├── core/           settings (fail-fast env), security (session tokens), errors (envelope)
│   │   ├── db/             Supabase client; ScopedTable (the user-isolation boundary); users, user_settings
│   │   ├── domain/         (planned) ledger, schedule (sen maths), providers, categorize, recurring detection
│   │   ├── engines/        (planned)
│   │   │   ├── forecasting/   financial health forecasting (component model + Monte Carlo)
│   │   │   └── risk/          BNPL risk classification (features.py, model, SHAP, counterfactuals)
│   │   ├── export_openapi.py  writes the OpenAPI document with no credentials (used by `npm run gen:api`)
│   │   └── seed.py         tester account seeding
│   ├── ml/                 (planned) datagen/, engine1_eval/, engine2_train/
│   ├── models/             (planned) served artefacts + metadata
│   ├── migrations/         0001_init.sql + how to apply it
│   ├── scripts/            seed_users.py, check_rls.py
│   └── tests/              unit tests on an in-memory fake (fakes.py); integration/ hits real Supabase; e2e_server.py backs Playwright
├── frontend/               Next.js app: app/ (login, (app) shell), components/, lib/ (session, api client + generated schema.d.ts), tests/unit + tests/e2e
├── data/                   (planned) personas/ (committed synthetic CSVs), external/ (download scripts), private/ (gitignored, never committed)
├── reports/                spikes/ so far; generated evaluation tables and figures later
└── refdocs/                PRD, status, decisions, plans, guides, context
```

## Documentation

| Doc | What's in it |
|---|---|
| [`refdocs/STATUS.md`](refdocs/STATUS.md) | Where the build actually is right now |
| [`refdocs/paysense-v2-PRD.md`](refdocs/paysense-v2-PRD.md) | Scope, architecture, both engine designs, roadmap, decision log |
| [`refdocs/changelog/CHANGELOG.md`](refdocs/changelog/CHANGELOG.md) | Session-by-session history |
| [`refdocs/changelog/DECISIONS.md`](refdocs/changelog/DECISIONS.md) | Why things are the way they are |
| [`refdocs/guides/env_setup.md`](refdocs/guides/env_setup.md) | Every environment variable and where to get it |
| [`refdocs/guides/checklist.md`](refdocs/guides/checklist.md) | Pre-ship checklist |
| [`refdocs/context/`](refdocs/context/) | v1 lessons, research brief, academic constraints, BNPL billing rules |
| [`refdocs/guides/kickoff-superprompt.md`](refdocs/guides/kickoff-superprompt.md) | The prompt that starts (or resumes) a build session |
| [`CLAUDE.md`](CLAUDE.md) | Operating brief for AI sessions on this repo |

## Data & privacy

This repository contains **no real personal financial data**. All personas and training data are synthetic, generated from published Malaysian statistics (sources in `refdocs/context/research-2026-10-08.md`). The predecessor prototype (PaySense v1) is published separately.

## License

Not yet chosen — all rights reserved until a license file is added.
