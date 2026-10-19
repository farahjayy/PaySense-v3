# Plan — Local completion round: the steps the cloud build could not do

> Execution: `refdocs/execution/2026-10-19-local-completion.md`. Source: `refdocs/fintechathon-2026/local-handoff.md`. The branch is `claude/local-dev`, cut from `main` at `c611f55`.

## 1. Why this exists
The cloud build did everything that needs no account of the author's and no change to the real database. What is left needs a Windows machine with the real Supabase project, the model provider keys and the downloads the cloud network blocked. Nothing here adds a feature; it proves the built system on real infrastructure and regenerates evidence from the final code.

## 2. Scope
**In:** a clean baseline on Windows (and a fix for any platform gap); applying migrations 0003 to 0006 and the real-database checks; the app run on the real database and walked in a browser; real-database evidence; live model runs; the real-data check of band rule R3 (task E, below); an ml-auditor pass; deployment; the env templates; the submission figures re-copied from regenerated reports.
**Out:** any new product feature; changing what is served unless a pre-registered rule below says to ask first; items J (G4, F7, starting-position reasons) unless time remains and each gets its own plan, ADR and pre-registered rule.

## 3. Real-data check of band rule R3 (task E), pre-registered
Written before any real-data number exists.

### 3.1 Data
MoneyData (one real UK account, spending and income series) and a seeded sample of Berka accounts, loaded exactly as the P3 evaluation loaded them (`ml.engine1_eval.loaders`). Raw files are gitignored. Both are benchmarks only (D-25): neither describes Malaysian students, and MoneyData is a single person.

### 3.2 Method
For each series and each origin from 17 weeks of history, stride 4: the point forecast of the served LSTM, the **served** error record (`served_error_record` with the served rule: the population record below 26 weeks, the user's own from 26, widened by the bucket factor), 300 simulated 13-week totals floored per the rule's clip, and the realised 13-week total. Reported per dataset, kind and history bucket (17-25, 26-38, 39-51, 52+): coverage of the P10-P90 band (nominal 0.80) and median bias. The same origins are scored under the v2 rule (R2: table of D-54, own record, weekly clip) and the single 1.5 factor (R1) so the comparison is on identical windows with the same random draws seed. Synthetic held-out numbers stay in `band_v3.md`; the report puts real beside synthetic and does not blend them.

### 3.3 Rule: R3 is "clearly worse" on real data if either holds
1. For histories of 26 weeks or more, pooled over both real datasets and both kinds, coverage(R3) < coverage(R2) - 0.05.
2. For histories of 17-25 weeks, pooled the same way, coverage(R3) < coverage(R2) - 0.05.

If either holds: write an ADR proposing what to do and **ask the author before changing what is served**. If neither holds: report the numbers, including how far each is from 0.80 and any cell that is worse than the synthetic one, and change nothing. Unflattering numbers go in the report either way; the rule only decides whether to propose a change.

## 4. Risks
- The Windows machine may differ from the Linux one in line endings (D-52): handled by pinning LF for the text artefacts and a test.
- `uv run` on this machine intermittently fails to reinstall the project package (access denied); the environment's own interpreter is used in that case.
- The real database has never run migrations 0003 to 0006; the in-memory fake may differ from the real service. Differences found are fixed with a failing test first.
- Live model runs depend on provider quotas (the free tier has a daily limit); failures are reported as they are, prompts are not tuned to hide them.
