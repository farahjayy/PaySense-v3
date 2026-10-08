"""Words for the Engine 1 report: the caveats and the README layout (plan P3, task B12)."""

import pandas as pd

DECIMALS = 4
SIGNIFICANCE = 0.05
MATERIAL_MASE_DIFFERENCE = 0.02  # a benchmark must lead by at least this much to override D-05
ALL_SOURCES = ("synthetic", "moneydata", "berka")

CAVEATS = """\
## Read this before trusting any number

- **MASE rewards forecasting the median; the product needs the running total.** Weekly MASE is an
  absolute error, so a model that forecasts the typical week scores well even when that week is
  zero (monthly allowances make more than half of synthetic income weeks zero). The cumulative
  margin table and the bias table show what that costs on the quantity Engine 2's label depends
  on. D-06 fixes MASE as the primary metric, so the rule uses it; the margin and bias results are
  reported beside the decision, never hidden, and the P4 residual bootstrap (which resamples the
  served model's own signed errors) is what must correct any systematic level bias.
- **The synthetic cohort is circular by construction.** The generator and these forecasters have
  the same author. The weekly series carries AR(1) drift, a payday-week lift, exam-week dips and
  outlier weeks (see `reports/datagen/README.md`); a model that happens to match them gains over
  a real series. MoneyData and Berka are reported separately and each counts as much as the whole
  synthetic cohort in the decision, so a single noisy real account (MoneyData has two series)
  carries a third of the metric. The per-dataset table shows whether the datasets agree.
- **All synthetic test series share one calendar** and the cohort has 78 weeks, so every test
  origin falls in the same half-year after the LSTM's cutoff week. Series are correlated through
  that shared calendar, which makes significance tests over them look stronger than they are.
- **Real data is not Malaysian students.** MoneyData is one UK adult's account; its weekly spend
  averages about GBP 1,170, so it probably includes movements between the owner's own accounts, and
  its spend includes fixed bills (no fixed/variable code). Berka is Czech bank accounts from
  1993-1998 with fixed payments removed by its own codes. Both are benchmarks only (D-25).
- **The global LSTM is trained on synthetic data only**, on weeks before the cutoff, with a fixed
  26-week input window (shorter histories are padded with their mean, which it never saw in
  training), and applied zero-shot to MoneyData and Berka. Pre-training it on Berka (D-25) was
  not done in this run.
- **Prediction intervals** are per-step empirical quantiles of the model's own earlier errors, the
  same for every model, and exist only once eight earlier errors for that step are observed. The
  product's 4-week moving-block bootstrap, which simulates whole paths, is built in P4.
- **No synthetic series has interval coverage.** The cohort is 78 weeks long and its test origins
  start at the LSTM's cutoff, so each series has only 13 origins and no origin ever has eight
  earlier errors for a 13-week step. Coverage evidence comes from MoneyData and Berka only (about
  0.6-0.75 against a nominal 0.8) and from the serving check in P4.
- **Income is evaluated as total weekly income.** Splitting it into confirmed and unconfirmed parts
  waits for recurring detection (P4).
- **Errors are scaled by the naive error of the whole history to date**, whatever history the model
  is shown, so the history-length figure compares models against the same yardstick.
- **Evaluated series are a seeded sample**, the same for every model, because Prophet and AutoARIMA
  are refitted at every origin. A series that any model failed on is dropped for all models before
  anything is averaged, and the count is printed above.
- **Windows and settings are fixed, not tuned on test origins:** moving averages of 4 and 13 weeks,
  AutoARIMA with season length 1, Prophet with yearly seasonality only above two years of history.
"""


def md_table(frame: pd.DataFrame) -> str:
    frame = frame.round(DECIMALS).fillna("")
    head = (
        "| " + " | ".join(map(str, frame.columns)) + " |\n"
        "|" + "|".join("---" for _ in frame.columns) + "|\n"
    )
    body = "".join("| " + " | ".join(str(v) for v in row) + " |\n" for row in frame.to_numpy())
    return head + body


def rule_text(horizon: int) -> str:
    return (
        "Rule (ADR D-06): serve the best literature candidate (ARIMA, Prophet, LSTM) by MASE at "
        f"{horizon} weeks, unless the best benchmark beats it by at least "
        f"{MATERIAL_MASE_DIFFERENCE} MASE with a Holm-adjusted Wilcoxon p < {SIGNIFICANCE}, in "
        'which case the benchmark is served and that is the finding. "MASE" here is the '
        "geometric mean over a dataset's series (so one series with a nearly flat history cannot "
        "decide the ranking), then the mean over datasets with equal weight; the plain arithmetic "
        "mean is shown beside it. Only series every model scored are used; the synthetic cohort is "
        "scored at the longest history shown to the models, and the rule is also applied at each "
        "shorter history (table below)."
    )
