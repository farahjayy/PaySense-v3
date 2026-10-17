# Deck outline (ten minutes or less)

> One idea per slide. Lead with measured results and the honest limits. Every figure is copied from the file named beside it; re-copy after any re-run. Use the same names as the app: PaySense, the forecast, the risk check, the assistant, Safe / Caution / At Risk.

| # | Slide | Content | Source of any figure |
|---|---|---|---|
| 1 | Think before you split | One line: PaySense tells a student whether a BNPL plan fits before they commit. The three faces. | — |
| 2 | The problem, for readers outside Malaysia | RM, the three providers, PTPTN once a semester, small instalments that stack. The context box from the technical documentation. | — |
| 3 | What a student sees | Dashboard screenshot: score, band, running-margin chart, alert. | screenshot from the live app |
| 4 | Ask in plain words | The assistant panel: the question, the risk card, "What I did" with the tiers, the confirm card. | `evidence/demo-run/SUMMARY.md` |
| 5 | The forecast, measured | Served LSTM vs ARIMA, Prophet and benchmarks: MASE 0.8153 vs 1.0438 for the best benchmark, 242 series, Holm-adjusted Wilcoxon. | `reports/engine1/README.md` |
| 6 | The risk check, measured | LightGBM + Platt: lockbox Brier 0.0142 vs logistic 0.0200 vs constant 0.1674; reasons from exact Shapley values; the smallest change, or "none does". | `reports/engine2/versions.md` |
| 7 | An assistant that cannot invent or act | Three tiers; no write tool; the number check; untrusted data; guided mode. Live evaluation 36 / 36 (and the run before the retry fix, 32 / 36, said out loud). | `reports/assistant/README.md` |
| 8 | Security | The controls in one diagram; the independent review; scans clean for the backend and the frontend's production dependencies; the known-risk list exists and is public. | `SECURITY.md`, `evidence/scans/SUMMARY.md` |
| 9 | Honest limits | The honest-limits paragraph in short: synthetic labels, risk mostly decided before the purchase, a band still too narrow for short histories; Safe on the demo personas only with a savings buffer. | `honest-limits.md`, `demo-scenario.md` |
| 10 | What is next | Real repayment outcomes with consent, a population error record for short histories, the deployed pilot. Thank you. | — |

Speaker timing: about a minute per slide; the demo video carries the walkthrough, so slides 3–4 stay short.
