# Plan — WP9 Execution evidence and demo script

> Execution: `refdocs/execution/2026-10-18-wp9-execution-evidence.md`. Scope: work-packages.md WP9.

## 1. Why this exists
Judges score what they can verify. Every claim in the submission should point to a file a script wrote: the demo run through the real API, the test outputs, the scans.

## 2. Scope
**In:** `scripts/demo_run.py` (section 6 end to end: opening turn, afford, safest option, go ahead → Confirm, bills, insights, budget → Confirm, messy paste with a duplicate → Confirm, an injected instruction in a description with the plans compared before and after, the small-purchase and savings-buffer contrast; transcripts, ids, the audit rows from the user's own export, timings; `--in-memory` or `--api`; `--render`); `scripts/collect_test_evidence.py` (every check with its output tail and a summary); `evidence/README.md` (how each folder is regenerated); the video recording script. Judge credentials are delivered privately, never in the repo (sandbox accounts come from `load_personas.py` against the deployed database, WP11).
**Out:** the recording itself (the author's).

## 3. Approach
The demo uses the persona accounts and the assistant's configured provider; without a key it runs in guided mode and says so. If "Go ahead with that." produces no proposal, the run sends one plain rephrasing, as a person would, and both turns are kept. Nothing in the summaries is typed by hand.

## 4. Definition of done
Both scripts tested; a live in-memory demo run with the real provider kept in `evidence/demo-run/`; test evidence regenerated at the final full run.
