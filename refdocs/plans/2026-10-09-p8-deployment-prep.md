# Plan — P8 Deployment preparation

> Execution: `refdocs/execution/2026-10-09-p8-deployment-prep.md`. Source of truth: PRD §6 (P8), ADR D-15.

## 1. Why this exists

Testers need a URL. P8 puts everything in place so that deploying is a sequence of dashboard steps the author can follow, and so that what is deployed has already been checked as far as it can be without the hosting accounts. **Nothing is deployed, pushed or paid for by this phase**: those are the author's decisions (CLAUDE.md rule 6; spending money and creating accounts are hers).

## 2. What's already covered

- Env-driven CORS and API URL (`CORS_ORIGINS`, `NEXT_PUBLIC_API_BASE_URL`); startup refuses to run with a missing variable.
- Security headers, body-size limit, login rate limiter, `--proxy-headers` guidance (env_setup.md).
- Engine 1 served through ONNX so the process never imports torch (D-15); measured memory in P4.

## 3. Scope

**In:** a runtime dependency audit (the API must run with only its declared runtime dependencies); a Dockerfile and `.dockerignore`; a Render blueprint; a nonce-based Content-Security-Policy for the frontend (deferred from the P1 reviews); production-build browser tests under that policy; a smoke script for a deployed API; a runbook with the live functional checklist, keep-alive options, rollback and the verified/not-verified table; `frontend/.env.example`.

**Out, with reasons:** creating accounts or projects, applying the migration, setting secrets, pushing, deploying (author); buying a plan (author); a CDN or custom domain (not needed for 5-7 testers); per-user write quotas and pagination (listed as known limits, not blocking at this scale); monitoring beyond Render's metrics.

## 4. Approach

- Build the production dependency set in a clean environment and run the app and a real forecast in it, so what is claimed about memory and imports is measured.
- Run the frontend as `next start` from a production build in the browser tests, so the CSP is enforced exactly as served.
- Keep every secret out of files: `render.yaml` uses `sync: false`; the runbook names variables only.
- The runbook says plainly what was and was not verified.

## 5. Risks & unknowns

| Risk | Confidence | Mitigation |
|---|---|---|
| The Dockerfile has never been built (daemon unavailable when prepared) | Medium that it builds first time | Short file; the runbook says where to look; Render's native Python runtime is a fallback |
| Render's proxy addresses for `FORWARDED_ALLOW_IPS` | Low until observed | Runbook gives an empirical check; the safe default (127.0.0.1) fails closed to "everyone shares one bucket" |
| Free-plan cold starts hurt a study session | High | Three options in the runbook, ranked; paying is the author's call |
| Nonce CSP forces dynamic rendering of every page | Certain | Accepted: all screens are per-user and client-fetched anyway; costs a server render per page view |
| `style-src 'unsafe-inline'` remains | Certain | Documented in `lib/csp.ts`; server-rendered `style=""` attributes cannot take a nonce |
| Supabase migration has never run | High that something needs a fix | Runbook step 2 says so and asks for the error text |

## 6. Definition of done

- The API imports and serves a forecast in a runtime-only environment; memory recorded.
- The production frontend sends a nonce CSP, every script carries the nonce, and the Playwright suite passes on desktop and phone profiles against it with no violations.
- `smoke_live.py` is tested against the real app.
- The runbook exists with the verified / not-verified table.
- STATUS and CHANGELOG record exactly that, and say nothing is deployed.
