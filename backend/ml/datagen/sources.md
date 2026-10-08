# Sources for the synthetic population parameters

> Read on 2026-10-08 with the web tools (not recalled from memory). Each entry says **what the page states**, **what was used**, and **what the page does NOT say** — because the generator's defensibility (supervisor's top concern, `academic-constraints.md` §2) rests on never presenting an assumption as a citation.
> A parameter in `params.yaml` either names one of the keys below in `source:` or carries `assumed: true` with a reason. The loader enforces this.

## ptptn_loan_table

- **Reference:** UniEnrol, "All you need to know about PTPTN", section 6 "How Much PTPTN Loan Can I Get? When Will I Receive?" — https://articles.unienrol.com/all-you-need-to-know-about-ptptn/ (a secondary source summarising PTPTN's published amounts).
- **States:** annual maximum loan by level and field; tiers "Maximum (STR/B40)", "75% (< RM8,000 household income per month)", "50% (> RM8,000)". **Public institution (IPTA) degree, Arts & Humanities:** max RM6,180, 75% = RM4,630, 50% = RM3,090. **Degree, Science:** max RM6,650, 75% = RM4,990, 50% = RM3,330. **Diploma:** max RM4,750, 75% = RM3,560, 50% = RM2,380. Loan is "based on the level and type of course and your family income bracket".
- **Used for:** the set of annual PTPTN amounts a public-university student may receive (`income.ptptn_annual_sen`).
- **Does NOT state:** how many disbursements there are per year or when. (An earlier research note in this repo said "2–3 disbursements"; this page does not support it, so the disbursement count and months are **assumed**.) Also does not say what share of students hold a PTPTN loan.

## tok_cheah_2024

- **Reference:** Tok & Cheah (2024), *International Journal of Banking and Finance* 19(1), 107–132, Universiti Utara Malaysia — https://e-journal.uum.edu.my/index.php/ijbf/article/view/20396 (abstract read; the open full text was truncated in retrieval, so only the abstract is used).
- **States:** primary survey, n = 454 students; "a large proportion of students spent between RM201 and RM400 per month"; spending corresponds to education level and income; higher spending is linked to being younger and male and to peer influence.
- **Used for:** the centre of the monthly discretionary-spend distribution for the budget-conscious persona (midpoint of the modal band, RM300) and the direction "spending rises with income".
- **Does NOT state (in the part read):** a mean, median, other bands, or income bands. The band is the *modal* band, not a population bound — students outside it exist.

## dosm_hes_2022

- **Reference:** Department of Statistics Malaysia, Household Expenditure Survey 2022 — https://www.dosm.gov.my/portal-main/release-content/household-expenditure-survey-report--malaysia--states- 
- **States (Malaysia, all households):** average monthly household consumption expenditure RM5,150 (2022). Shares: housing, water, electricity, gas and other fuels **23.2%**; food and beverages **16.3%**; restaurant and accommodation services **16.1%**; transport **11.3%**; these four total 66.9%.
- **Used for:** the *relative* weights of food : eating out : transport in the generator's discretionary category mix (16.3 : 16.1 : 11.3).
- **Does NOT state / limits:** shares for communication, education, recreation and the other groups were not on the page; and these are **households**, not students — they inform the mix of categories, not the level of student spending.

## ccob_repayment_2024

- **Reference:** RinggitPlus (Samuel Chua), "Over 168,000 BNPL accounts had overdue balances as at June 2025", 8 Aug 2025 — https://ringgitplus.com/en/blog/personal-finance-news/over-168000-bnpl-accounts-had-overdue-balances-as-at-june-2025.html , reporting the Deputy Finance Minister's Dewan Rakyat reply and a 2024 Consumer Credit Oversight Board Task Force study.
- **States:** among **21,000** active BNPL account holders, "almost **88%** made all payments on time", **12%** paid late but in full, "fewer than **0.5%**" could not repay in full. At 30 June 2025: 168,967 of 6.5 million BNPL customers (**2.6%**) had overdue balances totalling RM121.8 million (3.2% of the RM3.8 billion BNPL balance).
- **Used for:** the payment-behaviour mix of simulated instalments (on time / late but paid / missed). It feeds only the repayment-history *flag* demonstrations, never a model label (D-11).
- **Does NOT state:** the study's publication date; whether the 21,000 are students.

## bnm_fsr_2h2022

- **Reference:** NST Business, "Growing missed repayment among BNPL borrowers", 29 Mar 2023, reporting Bank Negara Malaysia's *Financial Stability Review, 2H2022* — https://www.nst.com.my/amp/business/home/2023/03/894114/growing-missed-repayment-among-bnpl-borrowers
- **States:** "about 44 per cent of BNPL users are aged between 18 and 30"; "more than 80 per cent of BNPL users earn less than RM3,000 a month"; the share of BNPL users with overdue payments was 7.0% (Q4 2021), 14.0% (Q2 2022) and 17.0% (the article labels the latest as both "second half of 2022" and "fourth quarter of 2022").
- **Used for:** context for the target population (young, lower-income) in the report's introduction; **not** for a parameter.
- **Note on a discrepancy:** 17% of users with overdue payments (BNM, 2H2022, a user-level measure) versus 2.6% of accounts overdue (Jun 2025, an account-level measure) are different measures at different dates; the generator uses the CCOB 88/12/0.5 split, and the report states this.

## bnpl_billing_rules_my

- **Reference:** `refdocs/context/bnpl-billing-rules-my.md` in this repo (researched 2026-09-25 from provider pages; the first-payment timing for SPayLater, TikTok PayLater and Atome was confirmed against real students' checkouts, D-24).
- **States:** SPayLater — nothing at checkout, first bill a month later; 0% for the 1-month plan (and 3-month on Shopee marketplace checkouts), about 1.5%/month on 12/18/24-month plans, limit RM2,500 to RM10,000. TikTok PayLater — nothing at checkout, about 1.5%/month on the 12-month plan, 0% on the 1- and 6-month plans, limit up to RM10,000. Atome — first payment on the purchase date, 3-payment plan at 0%, 6 and 12 months at 1.5%/month, limit varies by user.
- **Used for:** the instalment counts each provider offers, the fee rates, and the range of credit limits.
- **Does NOT state / limits:** the document itself lists unverified items (TikTok's late fee; whether SPayLater's 6-month plan is 0%; the billing cut-off). Limits are for the general user base, **not students specifically**.

## not_available

Figures the project looked for and could not obtain: the distribution of Malaysian students' **monthly income/allowance**; the share of students who hold a **PTPTN loan**; the share of students who use **BNPL** and how many concurrent plans they hold; typical **hostel/rent** costs from an official source; Tan et al. (2026) and Osman et al. (2024) demographics (cited in the literature review, not retrievable here). Every parameter that depends on one of these is `assumed: true` in `params.yaml` and appears in the report's limitations list.
