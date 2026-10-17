# Execution Plans

> **MANDATORY:** Every plan in `refdocs/plans/` that moves to implementation must have a matching execution document here.
> An execution plan covers **how** and **in what order** — ordered tasks, file paths, commands, and a Verify step per task.
> Do not start coding a feature that has no execution doc. Write one first.

## Naming convention

`YYYY-MM-DD-<slug>.md` — **identical filename to its companion plan** in `refdocs/plans/`. Same date, same slug.

## Required sections in every execution plan

1. **Companion plan** — link to the plan doc, at the top
2. **Before starting** — preconditions, env vars, what must already be green
3. **Tasks** — ordered and self-contained, each with:
   - the files it creates or modifies
   - the exact steps or commands
   - a **Verify** step: a real command and its expected result
4. **Wrap-up** — the STATUS / changelog / ADR checklist

**A task is done when its Verify passes** — not when the code compiles. That distinction is the entire value of this folder.

## Keeping these honest

If reality diverges from the doc mid-build, **edit the doc** and note it in the changelog's Deviations line. A plan that changed silently is a plan nobody trusts next time. Stale docs are worse than no docs.

## Index

| File | Companion plan | Status |
|---|---|---|
| [2026-10-08-p0-foundation.md](2026-10-08-p0-foundation.md) | [../plans/2026-10-08-p0-foundation.md](../plans/2026-10-08-p0-foundation.md) | In progress, all but live-Supabase checks |
| [2026-10-08-p1-ledger-bnpl.md](2026-10-08-p1-ledger-bnpl.md) | [../plans/2026-10-08-p1-ledger-bnpl.md](../plans/2026-10-08-p1-ledger-bnpl.md) | In progress, built and green on the in-memory database |
| [2026-10-08-p2-synthetic-population.md](2026-10-08-p2-synthetic-population.md) | [../plans/2026-10-08-p2-synthetic-population.md](../plans/2026-10-08-p2-synthetic-population.md) | Done |
| [2026-10-08-p3-engine1-evaluation.md](2026-10-08-p3-engine1-evaluation.md) | [../plans/2026-10-08-p3-engine1-evaluation.md](../plans/2026-10-08-p3-engine1-evaluation.md) | Done |
| [2026-10-08-p4-engine1-serving.md](2026-10-08-p4-engine1-serving.md) | [../plans/2026-10-08-p4-engine1-serving.md](../plans/2026-10-08-p4-engine1-serving.md) | Almost done |
| [2026-10-08-p5-engine2-training.md](2026-10-08-p5-engine2-training.md) | [../plans/2026-10-08-p5-engine2-training.md](../plans/2026-10-08-p5-engine2-training.md) | In progress |
| [2026-10-09-p6-engine2-serving.md](2026-10-09-p6-engine2-serving.md) | [../plans/2026-10-09-p6-engine2-serving.md](../plans/2026-10-09-p6-engine2-serving.md) | In progress |
| [2026-10-09-p7-frontend.md](2026-10-09-p7-frontend.md) | [../plans/2026-10-09-p7-frontend.md](../plans/2026-10-09-p7-frontend.md) | In progress |
| [2026-10-09-p8-deployment-prep.md](2026-10-09-p8-deployment-prep.md) | [../plans/2026-10-09-p8-deployment-prep.md](../plans/2026-10-09-p8-deployment-prep.md) | Done (nothing deployed) |
| [2026-10-09-p9-uat-kit.md](2026-10-09-p9-uat-kit.md) | [../plans/2026-10-09-p9-uat-kit.md](../plans/2026-10-09-p9-uat-kit.md) | In progress |
| [2026-10-15-p7b-ledger-polish.md](2026-10-15-p7b-ledger-polish.md) | [../plans/2026-10-15-p7b-ledger-polish.md](../plans/2026-10-15-p7b-ledger-polish.md) | Done (migration 0002 applied; Categories page verified on the real database) |
| [2026-10-13-import-spreadsheets.md](2026-10-13-import-spreadsheets.md) | [../plans/2026-10-13-import-spreadsheets.md](../plans/2026-10-13-import-spreadsheets.md) | Done (not yet tried with a real .xlsx in a browser) |
| [2026-10-18-wp1-real-run.md](2026-10-18-wp1-real-run.md) | [../plans/2026-10-18-wp1-real-run.md](../plans/2026-10-18-wp1-real-run.md) | Done (anon RLS check needs the anon key) |
| [2026-10-18-wp-api-contract.md](2026-10-18-wp-api-contract.md) | [../plans/2026-10-18-wp-api-contract.md](../plans/2026-10-18-wp-api-contract.md) | Done |
| [2026-10-18-wp18-login-hardening.md](2026-10-18-wp18-login-hardening.md) | [../plans/2026-10-18-wp18-login-hardening.md](../plans/2026-10-18-wp18-login-hardening.md) | Done on the in-memory database (migration 0003 not applied) |
| [2026-10-18-wp2-budgets.md](2026-10-18-wp2-budgets.md) | [../plans/2026-10-18-wp2-budgets.md](../plans/2026-10-18-wp2-budgets.md) | Done on the in-memory database (migration 0004 not applied) |
| [2026-10-18-wp13-bill-analysis.md](2026-10-18-wp13-bill-analysis.md) | [../plans/2026-10-18-wp13-bill-analysis.md](../plans/2026-10-18-wp13-bill-analysis.md) | Done |
| [2026-10-18-wp14-spending-insights.md](2026-10-18-wp14-spending-insights.md) | [../plans/2026-10-18-wp14-spending-insights.md](../plans/2026-10-18-wp14-spending-insights.md) | Done |
| [2026-10-18-wp15-recommendations-alerts.md](2026-10-18-wp15-recommendations-alerts.md) | [../plans/2026-10-18-wp15-recommendations-alerts.md](../plans/2026-10-18-wp15-recommendations-alerts.md) | Done |
| [2026-10-18-wp4a-tool-layer.md](2026-10-18-wp4a-tool-layer.md) | [../plans/2026-10-18-wp4a-tool-layer.md](../plans/2026-10-18-wp4a-tool-layer.md) | Done |
