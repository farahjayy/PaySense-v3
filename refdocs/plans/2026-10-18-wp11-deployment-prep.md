# Plan — WP11 Deployment (preparation)

> Execution: `refdocs/execution/2026-10-18-wp11-deployment-prep.md`. Scope: work-packages.md WP11.

## 1. Why this exists
The judges use a live URL. Everything that can be checked without the author's Render and Vercel accounts is checked here, so the deploy itself is a short, known sequence.

## 2. Scope
**In:** build and run the Docker image (never built before); smoke-test the container; rename the Render service (`paysense-v3-api`) so it cannot collide with v2's; the blueprint's assistant, token-budget, global-cap and quota variables; the deployment guide rewritten for v3 (migrations 0003–0006 first, persona accounts, the live demo run, the checklist with the assistant and the savings buffer); keep-alive options kept.
**Out (needs the author):** applying the migrations, creating the Render and Vercel services, the provider key in Render, `FORWARDED_ALLOW_IPS` from Render's proxy range, the smoke test and phone walkthrough on the live URL.

## 3. Definition of done (this session)
The image builds and starts with the models loaded; the smoke script's pre-login checks pass against it; the guide lists exactly what remains, in order.
