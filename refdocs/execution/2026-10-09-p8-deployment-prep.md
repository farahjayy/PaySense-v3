# Execution — P8 Deployment preparation

> Plan: `refdocs/plans/2026-10-09-p8-deployment-prep.md`. Tasks run top to bottom. Each task carries its own **Verify** step; a task is not done until its Verify actually passes.

## Before starting

- Read `CLAUDE.md`, `refdocs/guides/env_setup.md`, ADR D-15, `frontend/AGENTS.md` and `node_modules/next/dist/docs/01-app/02-guides/content-security-policy.md`.
- Rule 6: nothing is pushed, deployed or paid for here.

---

### Task H1 — Runtime dependency audit — DONE
- Built `uv sync --frozen --no-default-groups` in a separate environment; imported the app; checked every third-party import under `app/` resolves. `numpy` was only present through `onnxruntime`; declared it in `pyproject.toml` and relocked.
- **Verify:** import ok; all ten third-party roots resolve.

### Task H2 — Memory and latency in that environment — DONE
- Ran the API (in-memory database) in the runtime-only environment, imported a persona, made 30 forecast calls: 100 MB idle, 112 MB after, forecast p50 10 ms / p95 13 ms (warm).

### Task H3 — Container and blueprint — DONE, build not run
- `backend/Dockerfile`, `.dockerignore`, `render.yaml`. The Docker daemon was not running, so the image has not been built; recorded in the runbook.

### Task H4 — Nonce-based CSP — DONE
- `frontend/lib/csp.ts` (policy), `proxy.ts` (nonce per request), `app/layout.tsx` (`await connection()`), `next.config.ts` (CSP removed from static headers; HSTS added).
- **Verify:** unit tests on the policy; `next start` response carries the header and all 15 script tags on `/login` carry the matching nonce.

### Task H5 — Production-build browser tests — DONE
- Playwright now runs `npm run build && npm run start`; the e2e API server pins "today" next to the persona data and seeds one tester per browser project.
- **Verify:** `npx playwright test` — 12 passed (desktop and phone), CSP violations watched in the journeys.
- **Found on the way:** `frequent_bnpl.csv` stays locked (16 complete weeks); the locked message wrongly said "four months" when weeks were the shortfall. Message fixed; persona fix is P9 task U8.

### Task H6 — Smoke script and runbook — DONE
- `backend/scripts/smoke_live.py` (+ tests against the real app), `refdocs/guides/deployment.md`.

### Task H7 — Reviews
- `security-reviewer` on the web stack and deployment files; `react-reviewer`, `a11y-architect` on the frontend. Fix or list.

---

## Wrap-up (do not skip)

- [ ] `refdocs/STATUS.md`, `refdocs/changelog/CHANGELOG.md`
- [ ] ADR: nonce CSP with `style-src 'unsafe-inline'` (D-37 or next free id), PRD §7 one-liner
- [ ] env_setup.md: `FORWARDED_ALLOW_IPS`, `PORT`
- [ ] Next: the author's deployment (runbook), then P6/P7 completion
