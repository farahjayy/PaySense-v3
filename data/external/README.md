# External datasets (Engine 1 benchmarks)

Raw files are never committed (`data/external/**/raw/` is gitignored). Both datasets are real
transaction data of other people, used **only as benchmarks** for Engine 1 (ADR D-25); neither
models the target population (Malaysian students).

| Dataset | What | Licence | Fetch | Obtained |
|---|---|---|---|---|
| MoneyData | seven-plus years of one real UK retail account (8,315 rows) | CC BY 4.0 | `python data/external/moneydata/download.py` (checksum-verified) | yes, no login needed |
| Berka / PKDD'99 | 4,500 anonymised Czech bank accounts, 1,056,320 transactions (1993–1998) | the CTU page states none; published for research use | `cd backend && uv run python ../data/external/berka/download.py` (read-only public guest MariaDB account that the CTU dataset page publishes) | yes, no login needed |

Notes
- Berka's host `sorry.vse.cz` (the original archive) did not resolve; the CTU Relational Repository
  copy was used. Its server cancels long statements, so the script pages by primary key.
- Berka weekly series drop the fixed payment codes (SIPO, POJISTNE, UVER) and interest credits
  (UROK); see `backend/ml/engine1_eval/loaders/berka.py`.
- MoneyData weekly spending averages about GBP 1,170 a week, high for one person, so it probably
  includes large movements between the owner's own accounts that the dataset labels as ordinary
  debits. Every metric used here is scale-free, but the series is heavy-tailed; the report says so.
- The author's own private log (optional) would live in `data/private/` and is never committed.
