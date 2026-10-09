# UAT kit

Everything needed to run a short usability and decision study with a handful of testers on **synthetic persona data**. Nothing here collects real financial information.

| File | What it is |
|---|---|
| `participant-information.md` | One-page note handed to each tester |
| `task-script.md` | The facilitator's script for a session |
| `instruments.md` | SUS, explanation-clarity items, vignette questions, debrief |
| `vignettes.yaml` | The three decision scenarios, their options and the risk ordering the analysis uses |
| `templates/` | Blank response files: `sus.csv`, `clarity.csv`, `vignettes.csv` |
| `testers.template.csv` | Roster format: `participant,username,display,persona` |
| `data/example/` | **Invented** answers for six imaginary testers, to try the analysis script |

## Running a study

1. Copy `testers.template.csv` to `testers.csv` (gitignored), list your testers with participant codes and a persona each (`frequent_bnpl`, `budget_conscious`, `irregular_income`).
2. `cd backend && uv run python scripts/seed_testers.py --roster ../uat/testers.csv --dry-run`, then again without `--dry-run`. This needs `backend/.env` (see `refdocs/guides/env_setup.md`).
3. Run each session with `task-script.md`. The persona CSVs are in `data/personas/`.
4. Copy `templates/*.csv` into `uat/data/<run>/` and type each tester's answers in. This folder is gitignored; real answers never leave your machine unless you decide so.
5. `cd backend && uv run python -m ml.uat.analyse --data ../uat/data/<run> --out ../reports/uat/<run>.md`

The report gives mean SUS with a 95% confidence interval, the mean of each clarity item, and a before/after table per scenario showing how many testers chose a safer, the same or a riskier option (against the ordering in `vignettes.yaml`). With five to seven testers these are descriptive only, and the report says so.

## Persona dates

The persona statements were written for a fixed period. Imported unchanged on a later date, a tester would see a ledger months out of date and a forecast flagged as stale. Before a session, move the persona forward so it ends just before that day:

```
cd backend && uv run python -m ml.uat.shift_persona --persona budget_conscious     --session <the session date, YYYY-MM-DD> --out ../uat/data/budget_conscious_shifted.csv
```

Every date moves by the same whole number of weeks, so weekday patterns and the gaps between payments survive. Give the tester that file (not the original) for the import task. Do this on the day: a file shifted for one day is stale a fortnight later.

## Dry run

Run one full session with a friend before the real ones. Read the report it produces and check that every number matches what you recorded. Change `task-script.md` wherever the tester was confused by the script rather than by the app.

## Try the script without any data

`cd backend && uv run python -m ml.uat.analyse --data ../uat/data/example` prints a report marked **invented**. The marking comes from the first line of each example file; remove that line from a file and the banner goes with it, so never do that to the example.
