# PaySense v3 — Sources & References

> Raw research and external dependencies. The PRD is the *decided* view; this file is the *considered* view — including things that were looked at and rejected, which is often the more useful half.
> Record a source when it's chosen, and again when it's rejected. "We already tried that and here's why it didn't fit" is the single most expensive fact to re-derive.

Last updated: 2026-10-08

---

## Founding context documents

The documents this project was scaffolded from. Kept because the PRD paraphrases them and paraphrase loses detail.

| File | What it is |
|---|---|
| [context/v1-lessons.md](context/v1-lessons.md) | Sanitized audit of PaySense v1: what was built, what broke in each engine, what v2 ports |
| [context/research-2026-10-08.md](context/research-2026-10-08.md) | Three research passes (forecasting; risk modelling + Malaysian regulation; product/UAT/tech), every claim sourced and confidence-tagged |
| [context/academic-constraints.md](context/academic-constraints.md) | Supervisor decisions, examiner expectations, Interim Report methodology feedback |
| [context/bnpl-billing-rules-my.md](context/bnpl-billing-rules-my.md) | How SPayLater, TikTok PayLater and Atome bill in Malaysia (researched for v1) |
| `../PaySense/` (local, not in this repo) | v1 source — frozen, read-only reference for porting |

---

## External code & libraries

Versions are pinned in P0 after the dependency spike; nothing below is pinned yet.

| Name | What it does for us | Link | License | Status |
|---|---|---|---|---|
| FastAPI + uvicorn + Pydantic v2 | Backend API, validation, OpenAPI | https://fastapi.tiangolo.com | MIT | Chosen (v1 continuity) |
| supabase-py | Postgres access from the backend | https://github.com/supabase/supabase-py | MIT | Chosen (v1 continuity) |
| PyJWT | HS256 session tokens | https://pyjwt.readthedocs.io | MIT | Chosen (D-03) |
| pandas, numpy | Data handling | — | BSD | Chosen |
| statsforecast | AutoARIMA, Naive, WindowAverage, rolling-origin `cross_validation` | https://github.com/Nixtla/statsforecast | Apache-2.0 | Chosen — candidate implementation (P3) |
| prophet | Prophet candidate | https://github.com/facebook/prophet | MIT | Chosen — install on the pinned Python verified in P0 |
| PyTorch (CPU) | Global LSTM training | https://pytorch.org | BSD-3 | Chosen for training |
| onnxruntime | Serve the LSTM without PyTorch if memory requires (D-15) | https://onnxruntime.ai | MIT | Conditional |
| scikit-learn | Random Forest (`monotonic_cst`), logistic regression, calibration | https://scikit-learn.org | BSD-3 | Chosen |
| xgboost, lightgbm | Candidates with `monotone_constraints` | — | Apache-2.0 / MIT | Chosen |
| shap | TreeSHAP explanations | https://github.com/shap/shap | MIT | Chosen |
| optuna | Hyperparameter tuning (D-10) | https://optuna.org | MIT | Chosen |
| scipy, statsmodels | Statistical tests (Wilcoxon, Friedman), HLN-DM implementation support | — | BSD | Chosen |
| uv, Ruff, pytest, httpx | Python tooling | https://docs.astral.sh/uv | MIT / Apache-2.0 | Chosen |
| Next.js (App Router), React, TypeScript, Tailwind 4 | Frontend | — | MIT | Chosen (v1 continuity) |
| Recharts | Charts incl. P10–P90 band | https://recharts.org | MIT | Chosen (v1 continuity; React 19 may need a `react-is` override) |
| TanStack Query v5 | Server-state caching | https://tanstack.com/query | MIT | Chosen |
| zod | Form validation | https://zod.dev | MIT | Chosen |
| openapi-typescript + openapi-fetch | Generated API types and client (D-18) | https://openapi-ts.dev | MIT | Chosen |
| Vitest + Testing Library, Playwright | Frontend tests | — | MIT / Apache-2.0 | Chosen |

---

## APIs & services

| Service | Used for | Pricing model | Auth / key location | Status |
|---|---|---|---|---|
| Supabase (Postgres, Singapore region) | Database | Free tier (500 MB; pauses after 1 week idle) | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` in `backend/.env` | Chosen |
| Render | Backend hosting | Free (512 MB, sleeps after 15 min) | Dashboard env vars | Chosen (D-15) |
| Vercel (Hobby) | Frontend hosting | Free, non-commercial | Dashboard env vars | Chosen |
| Google Cloud Run | Backend fallback at 1 GiB | Always-free tier, billing account required | — | Fallback only (D-15) |
| Anthropic API (Claude Haiku 4.5) | Optional P10 explanation phrasing | Pay per use (~$0.0025 per explanation) | `ANTHROPIC_API_KEY` in `backend/.env` | Optional, not before P10 |

Keys live in `backend/.env` / `frontend/.env.local` (git-ignored) and are read server-side only — except `NEXT_PUBLIC_API_BASE_URL`, which is public by design. Never commit a key; never expose one to a client bundle.

---

## Reference material

Docs, papers, articles, repos studied but not depended on. Full citations with confidence tags: `context/research-2026-10-08.md`.

- Forecasting evaluation: Hyndman & Athanasopoulos, *Forecasting: Principles and Practice* (fpp3) — accuracy, tscv, prediction intervals chapters.
- Harvey, Leybourne & Newbold (1997) corrected Diebold–Mariano test.
- Bijak, Thomas & Mues — dynamic affordability assessment, *Journal of Credit Risk*.
- Nadeau & Bengio (2003) corrected resampled t-test (already used in v1's harness).
- Koklev — price of monotonicity in credit scoring, arXiv 2512.17945.
- Mothilal, Sharma & Tan (2020) DiCE; Ustun, Spangher & Liu (2019) actionable recourse.
- Consumer Credit Act 2025 (Act 873); BNM Policy Document on Personal Financing (30 Sep 2025); BNM Financial Stability Review 2H2025.
- Central Bank of Ireland RTP 15/2025 (BNPL behavioural mechanisms); AFM/Riverty reminder experiment; CFPB BNPL report (Jan 2025).
- MoneyData (CC BY 4.0) https://data.mendeley.com/datasets/dnxtg6n4rv/1; Berka / PKDD'99 https://relational.fel.cvut.cz/dataset/Financial.
- `monopoly` statement parser (AGPL-3.0) — reference only, PDF parsing is out of scope.

---

## Considered and rejected

| Option | Why it looked good | Why it lost | Recorded in |
|---|---|---|---|
| Chronos-2 / Chronos-Bolt foundation models | Zero-shot, CPU-capable, top of fev-bench, covariate support | Not in the literature review (D-05); evidence of gains on short, weakly seasonal series is mixed; torch on Render's 512 MB | D-05, future work |
| ETS / Theta / SCUM ensemble | Strong on short monthly series | Not in the literature review | D-05, future work |
| Explainable Boosting Machine | Glass-box, exact contributions | Not in the literature review | D-05, future work |
| v1's formula-based synthetic label | Continuity | The model just re-learned the formula; oracle ceiling | D-07 |
| Transfer from Give Me Some Credit / UCI Taiwan | Real default labels | Different population, no schedule features | D-07 (sanity check only) |
| Snorkel weak supervision | Combines noisy rules | Rules are the author's opinion again | D-07 |
| Supabase Auth (email / OAuth) | Real auth + RLS by `auth.uid()` | Supervisor ruled passwords/sign-up out of scope | D-03 |
| Hugging Face Spaces / Fly.io hosting | Generous CPU / RAM | Docker Spaces need PRO; Fly.io has no free tier | D-15 |
| `hey-api/openapi-ts` | Generates a full SDK + TanStack hooks | Young, changing fast; types-only is enough | D-18 |
| TimeGPT API | Strong zero-shot forecasts | Sends user financial data to a third party; paid | D-05 |
