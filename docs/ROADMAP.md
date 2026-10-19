# Roadmap

What PaySense does today, and what comes next. Items are in rough priority order, not on a schedule. The measured results behind "done" are in [`../reports/`](../reports/) and [`../evidence/`](../evidence/); the limits are in [`honest-limits.md`](honest-limits.md).

## Done

- [x] **Ledger:** transactions, CSV and Excel import, recurring income and bills, categories, BNPL plans for SPayLater, TikTok PayLater and Atome (plus a manual entry for any other provider), provider limits.
- [x] **Financial health forecasting:** a global LSTM benchmarked against ARIMA, Prophet, a naive forecast and moving averages; 1,000 simulated futures; the chance of running short.
- [x] **BNPL risk classification:** a calibrated LightGBM model, benchmarked against random forest, XGBoost and logistic regression; Safe / Caution / At Risk with reasons and the smallest change that would make it Safe.
- [x] **Second-Opinion Check:** what one purchase adds to the chance of running short, every instalment owed across providers, and a search for a safer time to buy.
- [x] **Topic A features:** budgets with a suggested budget, bill analysis, spending insights, ranked recommendations and alerts.
- [x] **Assistant:** plain-language requests over the app's own tools, three permission tiers, writes only after the student presses Confirm, a number check on every reply, guided mode without a model.
- [x] **Security:** hardened login, per-user scoping, quotas, an on-screen security drill over four attack classes, a published known-risk list ([`../SECURITY.md`](../SECURITY.md)).
- [x] **Privacy:** consent, export and delete-my-data; synthetic personas only.

## Next

- [ ] **Deploy** the backend (Render) and frontend (Vercel) and run the live checklist on a phone ([`deployment.md`](deployment.md)).
- [ ] **A student pilot** with the usability-testing kit in [`../uat/`](../uat/): SUS, explanation clarity, and whether the check changes decisions.
- [ ] **Real repayment outcomes, with consent,** to replace the synthetic training labels.
- [ ] **Forecast fixes the outcome check points to:** drift beyond 13 weeks, and bands for short histories on real accounts ([`../reports/engine1/outcome_check.md`](../reports/engine1/outcome_check.md)).
- [ ] **More providers:** named schedules for other BNPL providers once a real checkout example confirms each one's rules.
- [ ] **Bank-statement import** beyond CSV and Excel.

## Not planned

Bank or e-wallet API integration, credit-bureau checks, and investment tracking are outside PaySense's scope. It gives estimates from a student's own records; it is not financial advice or a credit decision.
