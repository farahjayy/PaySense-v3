# Engine v3 round: merge notes

> For the main session to fold into `CHANGELOG.md`, `STATUS.md` and `questions.md`, then delete. ADRs (D-60 to D-64), ASSUMED 50–53 and the PRD §7 rows are already in place. Plan and execution: `refdocs/plans/2026-10-18-engine-v3.md`, `refdocs/execution/2026-10-18-engine-v3.md` (commands and wall times there).

## Outcome against the pre-registered rules

- **Engine 1: band rule R3 is served** (monthly floor D-60, population record below 26 weeks D-61, refitted table). All four criteria held on a fresh group of 500 never-used students and on the outcome check.
- **Engine 2: v3 is served** (two-part target D-62, savings against outgoings D-63, labels version 4 made with R3, 11,000 profiles). All three criteria held. The two decisions were coupled (D-64): Engine 2 v2 cannot serve beside R3.

## Headline numbers (old → new, benchmarks beside)

Engine 1, fresh group F (500 students, 6,500 origins per kind; `reports/engine1/band_v3.md`):

| | x1.5 (R1) | served table (R2) | R3 | MA13 through R3 |
|---|---|---|---|---|
| inside P10–P90, spending (target 0.80) | 0.63 | 0.71 | **0.80** | 0.82 |
| inside P10–P90, income | 0.50 | 0.52 | **0.81** | 0.83 |
| 17–25 weeks, spending / income | 0.36 / 0.30 | 0.41 / 0.30 | **0.78 / 0.82** | 0.83 / 0.81 |
| median bias, spending / income (share of level) | +0.001 / +0.338 | +0.138 / +0.260 | **+0.006 / +0.012** | +0.003 / +0.007 |

Bootstrap over students, R3 − R2: coverage +0.090 (+0.079 to +0.101) spending, +0.284 (+0.263 to +0.305) income. MA13 through the same R3 method covers slightly more often than the LSTM; it is a benchmark on the band only (the LSTM still wins on P(shortfall), below).

Outcome check (2,000 students, P(shortfall) against what happened; `reports/engine1/outcome_check.md`):

| Brier | cut 13 weeks | cut 26 weeks |
|---|---|---|
| LSTM, R2 | 0.0199 | 0.0362 |
| LSTM, R3 | **0.0182** | **0.0309** |
| MA13, R2 / R3 | 0.0246 / 0.0228 | 0.0606 / 0.0652 |
| constant (in-sample) | 0.0470 | 0.1182 |
| R3 − R2 (95% interval over students) | −0.0018 (−0.0034 to −0.0004) | −0.0053 (−0.0073 to −0.0032) |

Unflattering, still true: where the month so far is zero or positive, the served P is still worse than a constant (cut 13: R3 0.0158, R2 0.0174, constant 0.0129; cut 26: 0.0225, 0.0258, 0.0120). R3 narrows the gap; it does not close it.

Recursion beyond 13 weeks (`reports/engine1/recursion_check.md`, new band section): from week 26, the R3 band holds the spending total 0.78 at 13 weeks but 0.49 at 52 (R2 0.71 → 0.47), median bias +0.012 → −0.122. The point forecast still drifts low (unchanged by this round). Long plans remain the least reliable labels.

Found while running: with R2, a user with exactly 17 weeks of history got a single-path fallback error record, which the path bootstrap can only replay: a band of zero width (P(shortfall) exactly 0 or 1). R3 replaces that record with the population record.

Engine 2 (`reports/engine2/README.md`, `versions.md`, `serving_check.md`):

| | v2 | v3 |
|---|---|---|
| lockbox | every tenth (scored twice before) | **new, indices 10,000–10,999, scored once** |
| lockbox Brier (constant) | 0.0142 (0.1674) | **0.0078** (0.1608) |
| lockbox Brier skill 1 − B/B_const | 0.9153 | **0.9514** |
| logistic benchmark | 0.0200 | 0.0126 |
| predict p_without benchmark | – | 0.0532 |
| p_without + mean added share | – | 0.0478 |
| lockbox band agreement | 0.918 | 0.948 |
| CV Brier (LightGBM; XGBoost tied, p = 0.35) | 0.0130 | 0.0070 |
| serving: same band as the direct simulation | 92.0% | **95.5%** |
| serving: mean absolute gap / largest | 0.053 / 0.473 | 0.021 / 0.368 |
| non-Safe results with a change that reaches Safe | 12.6% (14 of 111) | 16.0% (17 of 106) |
| of those, Safe by the direct simulation too | 85.7% | 76.5% |
| non-Safe results with no reason shown | 0.0% | **56.6%** |
| serving p95 | 0.45 s | 0.92 s (this machine; v2 was timed elsewhere) |

Old lockbox, continuity only (its third scoring, disclosed): Brier 0.0076, skill 0.953. Where the purchase moves the band (116 new-lockbox profiles): band agreement 76.7% (the constant also gets 76.7%, the logistic 69.8%), MAE of the added risk 0.144. The Engine 1 ablation shrinks to +0.0075 Brier (CI +0.0063 to +0.0087; v2 +0.0835), because the exact simulated base now carries most of the forecast's information. Monotone constraints cost 0.0010 Brier; 5 of 15 logistic signs disagree with the imposed directions (v2: 4).

Demo grid (`refdocs/fintechathon-2026/demo-scenario.md`): frequent_bnpl's chance without the phone is now 0.537 (was 1.000), so the RM600–799 phone visibly adds 0.21–0.27 instead of 0.000; still At Risk. With a RM1,000 buffer it becomes Caution with "6 instalments → Safe" (was At Risk, nothing reaches Safe); irregular_income with RM500 needs 6 instalments (was 4).

## Ready CHANGELOG entry

```
## 2026-10-18 — Engine v3 round (F1, F2, G1, G5): both engines replaced by pre-registered rules
- **Decided:** D-60 (monthly floor), D-61 (population error record below 26 weeks), D-62 (two-part Engine 2 target, reasons about the purchase), D-63 (savings in months of outgoings), D-64 (serve rules, coupling, new lockbox 10,000–10,999); ASSUMED 50–53. All "Claude decision, author to confirm".
- **Changed:** `simulate.py` (`clip`), `bands.py` (clip, population reference), new `population.py`, `service.served_error_record(s)` (one path for serving, labels and checks), `artefact.py` (`target`, `POPULATION_RECORD_SHA256`), `check.py` (`compose`), `assess.py` (scaled reasons), `features.py` (`savings_buffer_to_outgoings`, `DEFINITIONS_VERSION` v3), `templates.py`; `ml/engine1_eval/band_v3.py` (new), outcome and recursion checks run R2 and R3; `ml/engine2_train` two-part target in models/cv/calibrate/train/lockbox/stress/export/report/compare_versions; labels version 4 (11,000). Served files: `models/engine1/band_inflation.json` = `rules/v3`, `population_errors.json`, `models/engine2/v3/`. Reports: `reports/engine1/band_v3.md`, `outcome_check.md`, `recursion_check.md`, `reports/engine2/*` (v2 kept in `reports/engine2/v2/`), `demo-scenario.md`, `honest-limits.md`.
- **Results:** band coverage on 500 fresh students 0.71 → 0.80 (spending), 0.52 → 0.81 (income); outcome-check Brier 0.0199 → 0.0182 (13 weeks), 0.0362 → 0.0309 (26); Engine 2 new-lockbox skill 0.915 → 0.951, Brier 0.0078 against 0.0532 for "no added risk", same band as the simulation 92.0% → 95.5%; non-Safe results with no reason 0% → 56.6%.
- **Verified:** `cd backend && uv run ruff check . && uv run ruff format --check .` clean; `uv run pytest -q` (see the final count in the session report).
```

## STATUS lines

- Right now: Engine v3 round done: band rule R3 (monthly floor, population record below 26 weeks, refit) and Engine 2 v3 (two-part target, savings against outgoings) are served, each by a rule written before it ran (D-60 to D-64, author to confirm). No migration needed; the API contract is unchanged.
- WP16-style row: Engine v3 — band coverage on fresh students 0.80 / 0.81 (was 0.71 / 0.52); Engine 2 new-lockbox skill 0.951 (v2 0.915), same band as the simulation 95.5% (92.0%); "nothing stands out" for 56.6% of non-Safe results; real-data band check and G4 left.

## questions.md rows (author decisions)

| # | From | Question | What was done meanwhile |
|---|---|---|---|
| new | D-60–D-64 | Confirm the engine v3 ADRs (monthly floor, population record, two-part target with reasons scaled to the purchase, savings against outgoings, the serve rules and the new lockbox). | Built, evaluated and served under the pre-registered rules. |
| new | D-62 / ASSUMED 51 | With reasons about the purchase, 56.6% of non-Safe results say "nothing stands out" (the student was short before buying). Keep that (the without / with / added block explains it), or show the reasons of the starting position too? | Kept as built. |
| new | F9 (local) | Real-data check of R3 on MoneyData and Berka: `uv run python ../data/external/moneydata/download.py`, the Berka download, then `uv run python -m ml.engine1_eval.serving_check` (it still scores the v2 rules; extending it to R3 is a small change). Downloads are blocked in the cloud. | Synthetic-only evidence. |
| new | D-06 (local) | If F7 (iii) (hold the level or use MA13 beyond 13 weeks) is wanted, the per-horizon D-06 test needs the real datasets. | Not built; the recursion band section quantifies the drift. |
| new | G4 | Generator history mix (17–78 weeks) and near-zero-income students: Engine 2 still never sees a short history although the personas are about 21 weeks. Next round? | Not done (one relabel per round). |
| new | R3 vs MA13 | MA13 through the same R3 method covers the 13-week total slightly more often (0.82 / 0.83) but the LSTM keeps the lower outcome Brier (−0.0046 and −0.0343). Keep the LSTM (D-34). | LSTM served. |
| 22 | WP16 (C2) | Resolved by D-61 (population record) and D-60 (the income bias was the weekly floor): 17–25 weeks now 0.78 / 0.82. | — |
| 34 | ml-audit L2 | Resolved by D-63. | — |
| 38 | Engine 1 | Partly resolved: the band fixes are served; the recursion drift beyond 13 weeks (F7) remains. | — |
| 27 | WP16 | The old lockbox is now scored a third time (continuity only); v3's own lockbox is new and was scored once. | Disclosed in the reports. |

## Left for local

- F9 real-data band check (MoneyData, Berka) and the real-data D-06 part of any F7 change.
- Windows parity of the new artefacts (D-52): `population_errors.json` and the rule files are digested with LF line endings.
- `models/engine2/v2/` and `reports/engine2/v2/` are kept as the record; v2 no longer loads against this code (by design).
- The frontend was not touched; the API contract did not change, so `npm run gen:api` was not needed.
