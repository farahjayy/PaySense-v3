# Execution — P2 Synthetic population

> Plan: `refdocs/plans/2026-10-08-p2-synthetic-population.md`. Tasks run top to bottom. Each task carries its own **Verify** step; a task is not done until its Verify actually passes.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4).

## Before starting

- Read `CLAUDE.md`, `.claude/memory/preflight.md`, `refdocs/STATUS.md`, PRD §3.1, §3.2, §4 ("Data generation"), ADRs D-08, D-11, D-14, D-24, D-27, D-28, D-29, and `refdocs/context/{academic-constraints,research-2026-10-08,bnpl-billing-rules-my}.md`.
- Everything lives under `backend/ml/datagen/` and `backend/tests/ml/`. **`app/` must never import `ml/`** (CLAUDE.md "Surfaces"); `ml/` may import `app.domain` (schedule, plan builder, flows, categorize, money).
- All money is integer sen. All randomness comes from a `numpy.random.Generator` derived from a `SeedSequence`; no global `random`/`np.random` calls.
- The model-auditor agent (`ml-auditor`) is not needed here (no model is trained), but the generator's outputs are the training inputs for P5 — keep every parameter's provenance honest.

---

### Task A1 — Package skeleton and the `ml` dependency group
- **Files:** `backend/ml/__init__.py`, `backend/ml/datagen/__init__.py`, `backend/pyproject.toml` (a `[dependency-groups] ml = [...]`), `backend/tests/ml/__init__.py`, `backend/tests/ml/test_boundaries.py`.
- **Steps:** add `pyyaml`, `numpy`, `pandas`, `scipy`, `matplotlib` to an `ml` group (they are heavier than the API needs; the API gets `numpy`/`pandas` itself in P4). Install with `uv sync --group ml` (if uv hits the intermittent Windows `dist-info` lock, retry, or `uv pip install` then record it). `test_boundaries.py` greps `app/**/*.py` and fails if any file imports `ml`.
- **Verify:** `uv run python -c "import ml.datagen"`; `uv run pytest tests/ml/test_boundaries.py`.

### Task A2 — Sources and the parameter file (research task)
- **Files:** `backend/ml/datagen/sources.md`, `backend/ml/datagen/params.yaml`, `backend/ml/datagen/params.py`, `backend/tests/ml/test_params.py`.
- **Steps:**
  1. Open each primary source in the research brief (PTPTN 2026 rates, Tok & Cheah 2024 spend bands, DOSM HES 2022 category shares, CCOB/BNM repayment statistics, `bnpl-billing-rules-my.md`) with the web tools and record, in `sources.md`, the exact figure and where it was read. If a figure cannot be retrieved, say so — do not paraphrase from memory.
  2. `params.yaml`: grouped sections (income, bills, discretionary, bnpl, purchase, personas). Each leaf is `{value, unit, source: <key>}` or `{value, unit, assumed: true, why: "..."}`.
  3. `params.py`: pydantic models that load and validate the file; a leaf with neither `source` nor `assumed` is an error, and a `source` key must exist in `sources.md`. Expose `assumed_parameters()` and a stable `params_hash()`.
- **Verify:** `uv run pytest tests/ml/test_params.py` — provenance rule enforced (a fixture file missing both fields fails), every `source` resolves, the hash changes when a value changes, and the assumed list is non-empty and printable.

### Task A3 — Randomness and calendar utilities
- **Files:** `backend/ml/datagen/rng.py`, `backend/ml/datagen/calendar.py`, `backend/tests/ml/test_rng_calendar.py`.
- **Steps:** `profile_rng(master_seed, index)` = `Generator(PCG64(SeedSequence(master_seed).spawn(index+1)[index]))` (avoid O(n) by `SeedSequence(entropy=master_seed, spawn_key=(index,))`); week/month helpers (Mon–Sun weeks, month starts, semester boundaries, Malaysian public holidays are out of scope).
- **Verify:** `uv run pytest tests/ml/test_rng_calendar.py` — profile 7 is identical whether 10 or 100 profiles are requested; different indices give different streams.

### Task A4 — Income process
- **Files:** `backend/ml/datagen/income.py`, `backend/tests/ml/test_income.py`.
- **Steps:** three shapes — fixed monthly allowance (day-of-month, small variation), allowance + PTPTN lump sums (2–3 disbursements a year, amounts from the cited rates), irregular gig income (jobs per week ~ Poisson, pay ~ lognormal, occasional dry spells). Returns dated `IncomeEvent`s in sen plus the *ground-truth* recurring income spec (used later to score recurring detection).
- **Verify:** `uv run pytest tests/ml/test_income.py` — monthly totals within the parameters' ranges under a fixed seed; lump sums land in the right months; gig income has the stated dispersion; amounts are positive integers.

### Task A5 — Fixed bills and recurring items
- **Files:** `backend/ml/datagen/bills.py`, `backend/tests/ml/test_bills_gen.py`.
- **Steps:** rent/hostel (monthly or per-semester), phone/data, subscriptions, with exact dates and tiny amount jitter where real bills vary; output both the dated transactions and the ground-truth recurring items (name, amount, cadence, anchor).
- **Verify:** `uv run pytest tests/ml/test_bills_gen.py` — dates fall on the anchor day (month-end clamped like `add_months`); amounts stay within the stated jitter.

### Task A6 — Discretionary spending
- **Files:** `backend/ml/datagen/discretionary.py`, `backend/ml/datagen/merchants.py`, `backend/tests/ml/test_discretionary.py`.
- **Steps:** weekly total ~ over-dispersed positive distribution scaled to the persona's monthly spend; day-of-week profile; payday bump; exam-week dip; rare large outliers; split each week into merchant-style transactions with category mix from the cited shares. `merchants.py` holds description templates (English and Malay) chosen so `guess_category` recovers the intended category most of the time — and a documented minority of "unrecognisable" ones. Includes occasional refunds and own-account transfers so `Refund`/`Transfer` are exercised.
- **Verify:** `uv run pytest tests/ml/test_discretionary.py` — monthly median within the cited band; category shares within tolerance of the targets; `guess_category` agreement with the intended category ≥ the documented rate; weekly totals show the stated over-dispersion.

### Task A7 — Existing BNPL plans and their payment events
- **Files:** `backend/ml/datagen/bnpl.py`, `backend/tests/ml/test_bnpl_gen.py`.
- **Steps:** per persona, a count of existing plans, provider mix (assumed market weights unless cited), price distribution, instalment counts the provider offers, limits per provider; build each plan with `domain.plan_builder.propose_plan` (so the limit split and Atome checkout rule apply); emit instalment payments as linked `BNPL` expenses on or near due dates, with late/missed payments drawn from the cited repayment statistics. Missed/late behaviour feeds only the repayment-history *flag* demos (D-11), never a label.
- **Verify:** `uv run pytest tests/ml/test_bnpl_gen.py` — every plan passes `plans_repo`'s validation; sums equal the schedule exactly; the share of on-time payments matches the cited ~88% within sampling error over a large run; limits are respected.

### Task A8 — Proposed-purchase sampler (for Engine 2)
- **Files:** `backend/ml/datagen/purchase.py`, `backend/tests/ml/test_purchase.py`.
- **Steps:** price as a multiple of expected monthly income (log-uniform spanning trivial → well above a month's income, so Engine 2 sees clearly safe, borderline and clearly unaffordable cases), provider, instalment count among the provider's options, fee per the provider rule, and the limit split. Returns the same dict shape `propose_plan` takes.
- **Verify:** `uv run pytest tests/ml/test_purchase.py` — the price-to-income ratio distribution covers the intended range; each draw is a valid `propose_plan` input; the proposals include limit-capped ones.

### Task A9 — Profile assembler
- **Files:** `backend/ml/datagen/profile.py`, `backend/tests/ml/test_profile.py`.
- **Steps:** `generate_profile(params, master_seed, index, persona=None, history_months=...) -> StudentProfile` combining A4–A8 into: persona, demographics used only to *drive* generation (age and employment are never features, PRD §3.1), income/bills ground truth, a dated transaction list in app schema, existing plans with limits, one proposed purchase. History length is long enough for rolling-origin work (default 18 months; personas get exactly 4).
- **Verify:** `uv run pytest tests/ml/test_profile.py` — determinism (same seed ⇒ identical profile; 10-run is a prefix of a 100-run); every transaction passes `transactions._clean_row`; `month_summary` over the history matches the generator's own income/spend totals; no transaction is dated in the future.

### Task A10 — Persona CSVs and the importer round trip
- **Files:** `backend/ml/datagen/personas.py` (`python -m ml.datagen.personas`), `data/personas/{frequent_bnpl,budget_conscious,irregular_income}.csv`, `backend/tests/ml/test_personas.py`.
- **Steps:** one fixed seed per persona; export exactly 4 months as a bank-style CSV (`Date,Description,Amount`, dd/mm/yyyy, signed amounts, RM with two decimals) — the format the P1 importer parses. Include a few messy rows on purpose (a refund, an own-account transfer) so the importer's handling is exercised.
- **Verify:** `uv run python -m ml.datagen.personas` is byte-for-byte reproducible (run twice, compare hashes); `uv run pytest tests/ml/test_personas.py` imports each file with `parse_csv`, asserts no skipped rows, `history_span(...).distinct_months >= 4`, and income/spend within the persona's documented ranges. **The author reviews the three CSVs before P9.**

### Task A11 — Cohort and profile-set writers, manifest
- **Files:** `backend/ml/datagen/export.py` (`python -m ml.datagen.export`), `data/synthetic/MANIFEST.json` (committed), `data/synthetic/.gitignore` (outputs ignored), `backend/tests/ml/test_export.py`.
- **Steps:** write the Engine 2 profile set (JSON lines, default 10,000 — count is an argument) and the Engine 1 cohort (weekly discretionary-spend and unconfirmed-income series per profile, Parquet or CSV) to `data/synthetic/`; write a manifest with seed, params hash, counts, package versions.
- **Verify:** `uv run pytest tests/ml/test_export.py` on a small run (e.g. 50 profiles); `uv run python -m ml.datagen.export --profiles 1000 --out <tmp>` completes and the manifest matches; peak memory for 10,000 profiles recorded in the changelog (generation is streamed, not held in RAM).

### Task A12 — Distribution report
- **Files:** `backend/ml/datagen/report.py` (`python -m ml.datagen.report`), `reports/datagen/` (tables, figures, README), `backend/tests/ml/test_report.py`.
- **Steps:** from a fresh generation, tabulate each generated moment next to its cited target (monthly spend vs the RM201–400 band, income brackets, BNPL ownership, on-time repayment share, category shares), the assumed-parameter list, and a **limitations** section (circularity with the forecaster, assumed parameters, no real students). Figures by matplotlib. Everything is produced by the script; nothing is hand-edited (CLAUDE.md hard constraint 5).
- **Verify:** `uv run python -m ml.datagen.report` regenerates `reports/datagen/` and `git diff` afterwards is empty on a second run; `uv run pytest tests/ml/test_report.py` checks every cited target appears in the table and that the README names each `assumed` parameter.

---

## What actually happened (deviations from the tasks above)

- **A1–A3:** as written. Streams are `SeedSequence(entropy=master_seed, spawn_key=(index, crc32(stream)))`, so profile N is the same in a 10-run and a 10,000-run and a change to one component never shifts another.
- **A2 (sources):** the PTPTN page states annual loan amounts but not the number or timing of disbursements, so an earlier research note ("2–3 disbursements") is **not** supported; the count (2) and months (March, September) are assumed, and the research note is corrected in `sources.md`. Cited: 16 parameters; the rest are assumed (see the generated report for the current count).
- **A4–A5:** as written, with parameters added during the work (`exam_months`, `student_level_sigma`, `parttime_monthly_jitter`, `other_split_*`, `zero_fee_instalments.other`). Gig income uses the category "Gig". Part-time salary templates avoid the word "cafe" (the importer read "part time cafe" as Food). Bills truth records the *typical* amount, not the last month's.
- **A6 was redesigned twice, both times because of what the output looked like or what a reviewer found.** (1) The first persona CSVs showed implausible lines ("Uniqlo RM1.12"): a week's spend had been split into many tiny transactions regardless of category. (2) The ml-auditor then showed that the day-of-week and payday-day effects cancel out of any *weekly* sum, so the claim "richer than the forecaster" was false at the scale the forecasters see, and that category spend shares were biased (transport 0.23 vs a cited-implied 0.18). Now: the weekly series carries an AR(1) drift in the spending level, a payday-week lift, exam dips and outlier weeks (all assumed); a week's total is divided between categories (Dirichlet around the cited shares, a rare category appears only some weeks and then spends about a typical purchase), and each category's amount is cut into transactions of that category's typical size. Spend shares are now unbiased; the realised weekly total is slightly noisier than the drawn one.
- **A7:** `bnpl.py` exposes `build_proposal` and `unpaid_total_on` (reused by A8) and `BnplResult.actual_limits` (what each provider really allows, against `limits`, what the student has recorded). **Repayment is now drawn per student, not per instalment:** the cited 88 / 12 / <0.5% are shares of account *holders* (all on time / paid late / could not repay), and the first version applied them to each instalment, which made only ~37% of holders fully on time. A student is "always on time", "sometimes late" (their first due instalment is late, later ones with an assumed probability) or "misses one".
- **A8:** prices are log-uniform over 0.02–3.0 times monthly income (coverage, not realism; assumed). The plan is built against the limit the student has **recorded** only: with no recorded limit there is no cap (D-28), exactly as the app behaves. The first version used the true limit, which would have leaked information the app cannot see into the label and the `limit_known` feature.
- **A9:** `StudentProfile` also keeps `income_events` and `discretionary_events` (the same objects as in `transactions`). Demographics are not modelled as attributes at all: the persona drives generation and nothing else. `expected_monthly_income_sen` leaves PTPTN lump sums out (whether one falls in a 4-month window is calendar luck). `history_months` below 1 is rejected.
- **A10:** the persona is chosen as the first candidate profile in a fixed seed's sequence that shows what the persona exists to test (BNPL payments / gig income / break-even with neither) and that contains at least one refund and one own-account transfer. `.gitattributes` pins LF so the committed bytes match a regeneration, and `tests/ml/test_committed_artefacts.py` fails if a committed CSV, the manifest's parameter hash or the report no longer matches the code. **The author reviews the three CSVs before P9.**
- **A11:** the Engine 1 cohort is CSV (no new dependency). It carries total weekly income, not an "unconfirmed income" split, because which income is *confirmed* is decided by recurring detection in P4 (ASSUMED 10); the profile file keeps the recurring ground truth so P3/P4 can derive either. **Answer keys are nested under `truth`** in each profile (persona, generator-true income, true limits, recurring ground truth) and the cohort has no persona column, so a model cannot pick them up by accident; a P5 test must assert the feature code never reads `truth`. The manifest has no timestamp.
- **A12:** the moments table lists every cited parameter. Rows that hold by construction are labelled `cited (wiring check)`. Category rows use a 15% relative tolerance; repayment is compared per holder. The report runs on the same 10,000 profiles as the export. Three rows are reported without a pass/fail (eating-out share is generated jointly with food; derived rows have no cited target).
- **Reviews (python-reviewer, ml-auditor):** all HIGH findings fixed (window trimming tested at both ends, `history_months` validation, PTPTN-dependent pricing, purchase built from the recorded limit, per-holder repayment, the false "richer" claim); hardcoded assumptions moved into `params.yaml`; duplicate YAML keys rejected; list parameters returned as tuples; stale-artefact test added. **Not done, on purpose:** a golden test across machines/numpy versions (recorded as a limitation in the report), and a `PYTHONHASHSEED` subprocess test (the auditor ran one by hand: identical output under two seeds).

## Wrap-up (do not skip)

- [x] `refdocs/STATUS.md` — phase table, verification ledger
- [x] `refdocs/changelog/CHANGELOG.md` — session entry (include the list of `assumed` parameters and any cited figure that could not be retrieved)
- [x] `refdocs/changelog/DECISIONS.md` — ADR D-31 added; ASSUMED 6 restated, 7 and 8 added
- [x] This doc updated to match what actually happened
- [x] `python-reviewer` and `ml-auditor` on `ml/datagen` (findings applied; see above) · [ ] the author reviews the three persona CSVs before P9
- [x] File-structure doc written (the domain and ml layers now exist)
- [x] Next: `refdocs/plans/2026-10-08-p3-engine1-evaluation.md` + its execution doc (written)
