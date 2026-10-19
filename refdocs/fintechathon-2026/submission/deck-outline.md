# Deck outline (ten minutes or less)

> One idea per slide. Lead with measured results and the honest limits. Every figure is copied from the file named beside it; re-copy after any re-run. Use the same names as the app: PaySense, the forecast, the risk check, the assistant, Safe / Caution / At Risk.

| # | Slide | Content | Source of any figure |
|---|---|---|---|
| 1 | Think before you split | One line: PaySense tells a student whether a BNPL plan fits before they commit. The three faces. | — |
| 2 | The problem, for readers outside Malaysia | RM, the three providers, PTPTN once a semester, small instalments that stack. The context box from the technical documentation. | — |
| 3 | What a student sees | Dashboard screenshot: score, band, running-margin chart, alert. | screenshot from the live app |
| 3b | The Second-Opinion Check | Lenders must check your total commitments; nobody shows you. Without / with / adds, the month-by-month stack across providers, the RM 1,500 line, "Find a better time" → "Use this". The headline slide. | `demo-scenario.md` (*Adds*, *Safer timing*) |
| 4 | Ask in plain words | The assistant panel: the question, the risk card, "What I did" with the tiers, the confirm card. | `evidence/demo-run/SUMMARY.md` |
| 5 | The forecast, measured | Served LSTM vs ARIMA, Prophet and benchmarks: MASE 0.8153 vs 1.0438 for the best benchmark, 242 series, Holm-adjusted Wilcoxon. | `reports/engine1/README.md` |
| 6 | The risk check, measured | Two parts: the simulation gives the risk before the purchase, LightGBM + Platt the share it adds. New lockbox Brier 0.0078 vs logistic 0.0126 vs "no added risk" 0.0532 vs constant 0.1608; same band as the simulation 95.5%; the band holds the 13-week total 0.80 / 0.81 on fresh students. Reasons about the purchase; the smallest change, or "none does". | `reports/engine2/versions.md`, `reports/engine1/band_v3.md` |
| 7 | An assistant that cannot invent or act | Three tiers; no write tool; the number check; untrusted data; guided mode. Live evaluation 36 / 36 (and the run before the retry fix, 32 / 36, said out loud). | `reports/assistant/README.md` |
| 8 | Security | The security drill scoreboard: four named attack classes, model fooled in every attack, harm done in none; then the controls in one diagram, the independent review, clean scans, the public known-risk list. | `evidence/security-drill/SUMMARY.md`, `SECURITY.md`, `evidence/scans/SUMMARY.md` |
| 9 | Honest limits | The honest-limits paragraph in short: synthetic labels; the chance of running short is worse than a constant when the month so far is not negative; the forecast drifts low beyond 13 weeks; Safe on the demo personas only with a savings buffer. | `honest-limits.md`, `outcome_check.md`, `demo-scenario.md` |
| 10 | What is next | Real repayment outcomes with consent, the engine fixes the outcome check points to, the deployed pilot. Thank you. | `reports/engine1/outcome_check.md` |

Speaker timing: about a minute per slide; the demo video carries the walkthrough, so slides 3–4 stay short.
