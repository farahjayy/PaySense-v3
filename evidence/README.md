# Evidence

Everything here is written by a script; nothing is edited by hand. Regenerate with:

| Folder | What | Command |
|---|---|---|
| `tests/` | Every check a contributor runs (lint, format, types, unit and API tests with coverage, build, browser journeys), each output's last lines and a summary | `cd backend && PW_CHROMIUM_PATH=<chromium, if needed> uv run python scripts/collect_test_evidence.py` |
| `scans/` | pip-audit, npm audit, gitleaks over the whole history | `cd backend && uv run python scripts/run_security_scans.py` (gitleaks on PATH or `$GITLEAKS`) |
| `demo-run/` | The demo script (work-packages section 6) run end to end through the API: transcripts, proposal / plan / saved risk-check ids, the assistant's audit rows, timings | `cd backend && uv run python scripts/demo_run.py --in-memory` (or `--api <url>` against a running server with `load_personas.py` accounts) |
| `demo-scenario/` | The risk model's answers on the demo grid of purchases, with and without a savings buffer | `cd backend && uv run python scripts/find_demo_scenario.py --in-memory` (or `--api <url>`) |

The live assistant evaluation is in `reports/assistant/` (`scripts/assistant_eval.py --runs 3`). All personas are synthetic; no real person's data is in this folder.
