# Kickoff Superprompt — PaySense v3

> Paste everything below the line into a fresh Claude Code session opened at `C:\Users\User\Documents\College\FYP\PaySense_v2`. Written 2026-10-08 at the end of the scaffold session. Re-usable: if a session ends mid-build, paste it again — step 1 makes the new session resume from STATUS.md instead of starting over.

---

You are building **PaySense v3**, my Final Year Project at Universiti Teknologi PETRONAS: an AI-driven decision support system that helps Malaysian university students make informed BNPL purchasing decisions by combining **financial health forecasting** with **BNPL risk classification**, explained in plain language. This repo was scaffolded on 2026-10-08 with a complete project operating system. No application code exists yet. Your job is to build the whole product, phase by phase, to a finished, tested, deployable state.

## 1. Orient yourself first (do not skip)

Read, in this order, fully:
1. `CLAUDE.md`, then walk through `.claude/memory/preflight.md`
2. `refdocs/STATUS.md` — if anything is already built, resume from where it says; do not redo finished work
3. `refdocs/paysense-v3-PRD.md` — §3 holds the decided designs of both engines and the Engine 2 feature contract; §6 holds every phase's exit criteria
4. `refdocs/changelog/DECISIONS.md` — D-01 … D-25 are settled; do not re-debate them
5. `refdocs/context/` — `v1-lessons.md` (what broke in v1 and what to port), `academic-constraints.md` (supervisor decisions you must honour), `research-2026-10-08.md` (sources for every design choice), `bnpl-billing-rules-my.md`
6. `refdocs/plans/2026-10-08-p0-foundation.md` and `refdocs/execution/2026-10-08-p0-foundation.md` — your first phase

Then tell me in ≤ 10 lines: the phase you're starting, the open `ASSUMED:` items, and anything in the docs that contradicts something else (quote both — don't resolve it silently).

## 2. How to work

Build straight through the roadmap **P0 → P1 → … → P9** without waiting for my confirmation between phases. P10 (LLM-phrased explanations) only after P0–P9 are green, and ask me first.

For every phase:
1. **Plan.** If the plan + execution pair doesn't exist, write it first with the `feature-planner` agent / `/plan-feature` (P0's pair already exists). Ports from v1 name the exact files and tests.
2. **Build test-first.** Red → green → refactor, ≥ 80% coverage on `backend/app` and `frontend/lib`. Read the real docs of every library before using it — never code an API from memory.
3. **Review.** After writing code, run the `code-reviewer` agent, plus `python-reviewer` / `typescript-reviewer` / `react-reviewer` as relevant. Run `security-reviewer` for auth, imports, and anything touching user input or the database. For any change under `backend/app/engines/` or `backend/ml/`, run the project's `ml-auditor` agent **before** training or exporting artefacts. Fix CRITICAL and HIGH findings.
4. **Verify.** Every execution-doc task's Verify step must actually pass; run the `test-runner` agent at the end of each phase. Check the phase's exit criteria in PRD §6 one by one.
5. **Record.** `/session-end` duties at each phase end: CHANGELOG entry with an honest Verified line, STATUS phase table + verification ledger, ADRs for new decisions (same id in PRD §7), resolved `ASSUMED:` items, execution doc edited to match what really happened, index tables updated.
6. **Commit.** Conventional commits at the end of each verified task group. **Never push** unless I ask — this repo's remote is `origin` = `https://github.com/farahjayy/PaySense-v2` (public), and the GitHub CLI is installed and logged in as `farahjayy` on this machine if I do ask.
7. **Report.** At each phase end, give me ≤ 8 lines: what was built, what was verified (commands + results), deviations, and anything that needs me.

## 3. Non-negotiables (full list in CLAUDE.md)

- **This repo is public.** No real personal financial data, no secrets. Real data only in gitignored `data/private/`. Personas and training data are synthetic.
- **Candidate algorithms are fixed by my literature review:** ARIMA / Prophet / LSTM (financial health forecasting), Random Forest / XGBoost / LightGBM (BNPL risk classification), SHAP. Only the benchmarks and configurations in D-05 may be added.
- **Engine 1** is the component forecaster in PRD §3.1: known flows placed on exact dates, only weekly variable series (discretionary spend; income when unconfirmed) forecast, residual-bootstrap Monte Carlo (1,000 paths), **no starting balance** (D-27): monthly margin, P(shortfall) = cumulative margin < RM0 at a month-end. Provider limits cap the financed amount and the excess is paid at checkout (D-28).
- **Engine 2's label is Engine 1's simulated shortfall probability** (D-07). Features are computed **only** in `backend/app/engines/risk/features.py` (D-09), with a schema hash checked at startup. Repayment history is a separate flag, not a feature (D-11).
- **Every DB query is user-scoped** (username-only login, D-03), with isolation tests.
- **No fabricated numbers** anywhere — UI, reports, or contingency paths. Evaluation tables and figures are generated by scripts in `backend/ml/` into `reports/`, with benchmarks always included and results reported even when unflattering.
- **v1 at `C:\Users\User\Documents\College\FYP\PaySense` is read-only** — port from it (list in `refdocs/context/v1-lessons.md` §5), never edit it.
- **BNPL providers (D-24):** only SPayLater, TikTok PayLater and Atome are named and rule-driven. Every other provider uses the manual "Other provider" entry — the user types the first payment date, number of instalments and the instalment amount (or total payable) from their checkout, and the app splits it exactly in sen with no provider rule or fee formula. Do not add Grab PayLater, Boost PayFlex or any other provider's rules unless I give you a real checkout example.
- **Berka (D-25) is a benchmark only:** real Czech bank-account series for comparing the forecasters and pre-training the global LSTM — never a model of the target users. PaySense's users are Malaysian university students with a bank account and e-wallets but usually no credit card; the student population comes from the cited synthetic generator (D-08).
- **Money is integer sen.** Terminology in UI and reports: "financial health forecasting" and "BNPL risk classification".
- **No deadlines, dates or schedule talk** in plans, docs or reports — phases are dependency-ordered only.

## 4. The only reasons to stop and ask me

- Supabase credentials (P0): I create the project (Singapore region) and put the URL and secret key into `backend/.env` myself — tell me exactly when you need them, and keep building everything else meanwhile.
- Applying SQL migrations to Supabase if you can't do it from code — give me the file to paste into the SQL editor.
- A dataset download that needs my login.
- Anything that would contradict an ADR or a supervisor decision in `academic-constraints.md`.
- Pushing, deploying to Vercel/Render (P8 needs my accounts — prepare everything, then hand me the exact steps), or spending money.

**Already settled — do not ask again:** UAT does not need ethics/consent approval (testers use synthetic persona data only; write a short participant information note, not a consent form); Berka may be used as a benchmark (D-25); candidate algorithms stay within the literature review (D-05); only three named BNPL providers (D-24); no deadlines or timeline framing, ever.

Everything else: decide, record it (`ASSUMED:` or an ADR), and keep going.

## 5. Definition of finished

All of P0–P9 are ✅ in STATUS.md with a verification-ledger row each, and:
- A tester can log in with a username → import a persona CSV → see the dashboard with a 3-month margin band and health score → run a BNPL risk check → see Safe/Caution/At Risk, the reasons, the "what would make this Safe" suggestions and the with/without monthly-margin chart → confirm it into a plan → open its frozen risk report — on desktop and a phone browser.
- `reports/engine1/` and `reports/engine2/` contain the generated comparison tables and figures the dissertation needs (candidate comparison with benchmarks and significance tests, calibration, ablation proving the forecast's contribution, stress tests), each with a short README explaining how it was produced.
- The UAT kit (P9) is ready: tester seeding script, 3 persona CSVs, task script, SUS + explanation-clarity + pre/post decision instruments, a short participant information note, and an analysis script that has been run on dry-run data.
- Final report to me: what was built, every test/eval command and result, model winners with their numbers, deviations from the PRD, known limitations, and the exact commands to run the app locally.

Start now with step 1.
