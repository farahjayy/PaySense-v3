# Plans

> **MANDATORY:** Before implementing any non-trivial feature, a plan document must exist in this folder.
> A plan covers **what** and **why** — goal, scope, constraints, risks, definition of done.
> The **how** and **in what order** belongs in `refdocs/execution/`. When the two merge, both stop being read.

## Naming convention

`YYYY-MM-DD-<slug>.md` — the date the plan was written, then a short kebab-case slug. Phase plans use the phase id in the slug (`p1-ledger-bnpl`, `p3-engine1-evaluation`, …).

**The execution doc uses the identical filename** in `refdocs/execution/`. Same date, same slug — that mirroring is how you find a plan's other half without opening anything. If a plan gets superseded, write a new one and mark the old row Superseded; don't rewrite history in place.

## Required sections in every plan

1. **Why this exists** — the problem, in the user's terms
2. **What's already covered** — what needs no work, so nobody rebuilds it
3. **Scope** — what's in, and what's explicitly out *with reasons*
4. **Approach** — the shape of the solution
5. **Risks & unknowns** — with honest confidence levels. "I read this library's docs" and "I think this library does that" are different rows.
6. **Definition of done** — phrased as observable facts, not intentions

## Index

Add a row when you write a plan. Update the status when it moves — a stale index is how a project ends up with three plans for the same thing.

Status vocabulary: `Draft` · `In progress` · `Done` · `Blocked` · `Superseded` · `On hold`

| File | Description | Status |
|---|---|---|
| [2026-10-08-p0-foundation.md](2026-10-08-p0-foundation.md) | P0 Foundation — toolchain spike, backend/frontend skeletons, username login + user scoping, generated API client, test tooling | In progress, all but live-Supabase checks |
| [2026-10-08-p1-ledger-bnpl.md](2026-10-08-p1-ledger-bnpl.md) | P1 Ledger & BNPL domain — pure-domain ports (schedule, limit split, flows, CSV), repositories, API; no balance (D-27) | In progress, built and green on the in-memory database |
| [2026-10-08-p2-synthetic-population.md](2026-10-08-p2-synthetic-population.md) | P2 Synthetic population: cited parameter file, deterministic generator, persona CSVs, Engine 2 profiles, Engine 1 cohort, distribution report | Done |
| [2026-10-08-p3-engine1-evaluation.md](2026-10-08-p3-engine1-evaluation.md) | P3 Engine 1 evaluation: five forecasters, rolling origin, MASE and significance; the global LSTM wins (D-34) | Done |
| [2026-10-08-p4-engine1-serving.md](2026-10-08-p4-engine1-serving.md) | P4 Engine 1 serving: recurring detection, Monte Carlo, /api/forecast, the LSTM through ONNX | Almost done |
| [2026-10-08-p5-engine2-training.md](2026-10-08-p5-engine2-training.md) | P5 Engine 2 training: simulation labels, shared features, four classifiers, lockbox, calibration, ablation, stress | In progress |
| [2026-10-09-p6-engine2-serving.md](2026-10-09-p6-engine2-serving.md) | P6 Engine 2 serving: risk check, SHAP factors, counterfactual search, repayment flag, frozen report | In progress |
| [2026-10-09-p7-frontend.md](2026-10-09-p7-frontend.md) | P7 Frontend: all screens, states, accessibility, browser journeys | In progress |
| [2026-10-09-p8-deployment-prep.md](2026-10-09-p8-deployment-prep.md) | P8 Deployment preparation: container, blueprint, nonce CSP, runbook, smoke script | Done (nothing deployed) |
| [2026-10-09-p9-uat-kit.md](2026-10-09-p9-uat-kit.md) | P9 UAT kit: instruments, roster seeding, persona dates, analysis script | In progress |
| [2026-10-15-p7b-ledger-polish.md](2026-10-15-p7b-ledger-polish.md) | P7b Ledger polish: spending by category, categories, plainer wording, Excel guard, month names | Done (migration 0002 applied; Categories page verified on the real database) |
| [2026-10-13-import-spreadsheets.md](2026-10-13-import-spreadsheets.md) | Import: Excel workbooks, and a file's own Type and Category columns taken as written | Done (not yet tried with a real .xlsx in a browser) |
| [2026-10-18-wp1-real-run.md](2026-10-18-wp1-real-run.md) | WP1 Real run: real database, uvicorn, smoke, persona accounts, demo scenarios, real-model journey | Done (anon RLS check needs the anon key) |
| [2026-10-18-wp-api-contract.md](2026-10-18-wp-api-contract.md) | WP-API Contract first: stub routes and typed shapes for budgets, insights, recommendations, alerts, assistant | Done |
| [2026-10-18-wp18-login-hardening.md](2026-10-18-wp18-login-hardening.md) | WP18 Login and abuse hardening: passphrase, token revocation, write quota, ledger cap, pagination, plan-create lock (D-49) | Done on the in-memory database (migration 0003 not applied) |
| [2026-10-18-wp2-budgets.md](2026-10-18-wp2-budgets.md) | WP2 Budgets backend: per-category monthly limits, status with pace, suggest a budget | Done on the in-memory database (migration 0004 not applied) |
| [2026-10-18-wp13-bill-analysis.md](2026-10-18-wp13-bill-analysis.md) | WP13 Bill analysis: recurring bills, increases, 7-day collisions, next 30 days due | Done |
| [2026-10-18-wp14-spending-insights.md](2026-10-18-wp14-spending-insights.md) | WP14 Spending insights: movers, unusual transactions, savings rate, rule-chosen headline | Done |
| [2026-10-18-wp15-recommendations-alerts.md](2026-10-18-wp15-recommendations-alerts.md) | WP15 Ranked recommendations and proactive alerts over engine outputs | Done |
| [2026-10-18-wp4a-tool-layer.md](2026-10-18-wp4a-tool-layer.md) | WP4a Assistant tool layer: registry, tiers, executor, guided run | Done |
| [2026-10-18-wp4b-pending-actions.md](2026-10-18-wp4b-pending-actions.md) | WP4b Pending actions, confirm endpoint, audit log (D-48) | Done on the in-memory database (migration 0004 not applied) |
| [2026-10-18-wp4c-llm-loop.md](2026-10-18-wp4c-llm-loop.md) | WP4c LLM loop and guardrails, provider-agnostic (D-47, D-53) | Done (Gemini live; Anthropic mocked) |
| [2026-10-18-wp4d-import-by-chat.md](2026-10-18-wp4d-import-by-chat.md) | WP4d Import by chat: grounded parsing of pasted transactions | Done |
| [2026-10-18-wp19-privacy.md](2026-10-18-wp19-privacy.md) | WP19 Privacy: consent, export my data, delete my data, responsible use | In progress |
| [2026-10-18-wp3-topic-screens.md](2026-10-18-wp3-topic-screens.md) | WP3 Budgets, insights, recommendations screens; WP19 consent and data screens | Done |
| [2026-10-18-wp6-assistant-evaluation.md](2026-10-18-wp6-assistant-evaluation.md) | WP6 Assistant scenario and security suites, live evaluation | Done (32/33 live turns on gemini-3.1-flash-lite) |
| [2026-10-18-wp8-security-self-assessment.md](2026-10-18-wp8-security-self-assessment.md) | WP8 SECURITY.md, threat model, known risks, pip-audit / npm audit / gitleaks evidence | ✅ Done |
| [2026-10-18-wp16-engine-update.md](2026-10-18-wp16-engine-update.md) | WP16 Engine update: savings buffer in both engines (D-50), band widening by history length (D-54), bias-term sensitivity (D-56) | Done; migration 0005 not applied; real ml-auditor run pending |
| [2026-10-18-wp17-engine-follow-ups.md](2026-10-18-wp17-engine-follow-ups.md) | WP17 honest limits, model page (fairness, assistant, limits), checkout question | ✅ Done |
| [2026-10-18-wp7-ui-flow-polish.md](2026-10-18-wp7-ui-flow-polish.md) | WP7 first screen, Try this, budget strip, login wording, local terms, phone widths | ✅ Done |
| [2026-10-18-wp9-execution-evidence.md](2026-10-18-wp9-execution-evidence.md) | WP9 demo run through the API, test evidence collector, video script | ✅ Done |
| [2026-10-18-wp10-repo-licence-docs.md](2026-10-18-wp10-repo-licence-docs.md) | WP10 README, THIRD_PARTY, CREDITS, file structure, torch-free tests | ✅ Done |
| [2026-10-18-wp11-deployment-prep.md](2026-10-18-wp11-deployment-prep.md) | WP11 Docker image built and run, smoke, blueprint, deployment guide (deploy needs the author) | 🔶 Prepared; deploy needs the author |
