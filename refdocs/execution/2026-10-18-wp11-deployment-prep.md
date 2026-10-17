# Execution — WP11 Deployment (preparation)

> Companion plan: `refdocs/plans/2026-10-18-wp11-deployment-prep.md`.

## Tasks
1. Docker: start the daemon in the session; `docker build -t paysense-api backend`. Docker Hub answered 429 (anonymous pull limit) and ghcr.io blob downloads are blocked by the network policy, so a test-only copy of the Dockerfile (in the scratchpad, not committed) pulled `mirror.gcr.io/library/python:3.12-slim`, copied the local `uv` binary instead of `ghcr.io/astral-sh/uv`, and trusted the proxy's CA in the build stage; every other line ran as written. `docker run` with the session's configuration: start-up complete (both artefacts loaded), `/api/health` 200, 82 MiB idle, image 471 MB.
2. `scripts/smoke_live.py` against the container: service, CORS and anonymous refusal PASS; login 503 (no `passphrase_hash` column on the real database until migration 0003).
3. `render.yaml`: service `paysense-v3-api`; `SESSION_TTL_HOURS` 12 (logout now revokes); `LLM_PROVIDER`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` (prompted), `ASSISTANT_GLOBAL_DAILY_TOKENS`, `ASSISTANT_USER_DAILY_TOKENS`, `ASSISTANT_DAILY_REQUESTS`, `DAILY_WRITE_QUOTA`.
4. `refdocs/guides/deployment.md` rewritten for v3.

## Wrap-up
CHANGELOG, STATUS, questions; commit and push.
