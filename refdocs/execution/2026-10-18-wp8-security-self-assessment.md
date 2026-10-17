# Execution — WP8 Security self-assessment and scans

> Companion plan: `refdocs/plans/2026-10-18-wp8-security-self-assessment.md`.

## Tasks
1. `SECURITY.md`. Verify: every control row names code and a test that exist (grep).
2. `backend/scripts/run_security_scans.py`. Verify: `cd backend && uv run python scripts/run_security_scans.py` writes `evidence/scans/*.json` and `SUMMARY.md`; ruff clean.
3. Independent security review (review agent, read-only). Verify: each finding fixed with a test or recorded as a known risk in `SECURITY.md`.

## Deviations
- pip-audit audits the pinned list without installing (`--no-deps --disable-pip`): the install-based audit failed on the CPU torch wheel, which is not on PyPI.
- gitleaks is not packaged for this environment; the release binary is used through `$GITLEAKS`.

## Wrap-up
CHANGELOG, STATUS; commit and push.
