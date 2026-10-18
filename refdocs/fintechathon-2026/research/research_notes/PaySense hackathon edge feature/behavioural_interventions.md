# Behavioural-finance interventions that measurably change BNPL and short-term credit decisions

Scope: what the evidence says about BNPL overspending, which point-of-decision interventions move behaviour (with effect sizes), AI/chatbot delivery, counterfactual explanations, Malaysia/ASEAN student evidence, and which intervention to build and test in a small UAT. Search-only session: several primary PDFs (Central Bank of Ireland, BIT-style UK report, arXiv survey) could not be fetched (DNS failures), so some figures come from search-engine abstracts and summaries. Those are flagged.

## 1. What the empirical literature shows about BNPL usage and overspending

### Takeaway
BNPL access raises spending, especially at retail and among liquidity-constrained or low-credit-score buyers. Reported effects: merchant sales up about 20%, spending about 4.4% higher in an experiment, and a 22% higher chance of a discretionary purchase through "phantom liquidity". New BNPL users show rising overdraft and credit-card fees. Most of this evidence is observational (or uses quasi-experimental designs), and the direction of causality is not settled. Young adults are over-represented in missed payments.

### Cited Findings
- **Di Maggio, Katz & Williams (NBER WP 30508, 2022):** BNPL access raises total spending and the retail share of spending. The magnitudes are "too large" for standard intertemporal or static substitution effects. The authors say the results fit a "liquidity flypaper effect", in which BNPL liquidity "sticks where it hits". — [NBER w30508](https://www.nber.org/system/files/working_papers/w30508/w30508.pdf); [RePEc](https://ideas.repec.org/p/nbr/nberwo/30508.html)
- Same paper: for liquidity-constrained users, BNPL raises total spending **and overdraft fees** but also helps them smooth spending. The shift toward retail appears even among credit-card holders, who presumably have enough liquidity. — [NBER w30508](https://www.nber.org/system/files/working_papers/w30508/w30508.pdf)
- **Berg, Burg, Keil & Puri (NBER WP 33152 2024; J. Financial Economics vol. 171, 2025):** BNPL **raises merchant sales by 20%**, driven by customers with low creditworthiness and by products where the merchant has more market power. In effect it bundles the product with a subsidised loan, which lets merchants price-discriminate. (The identification design and the German-retailer setting were not confirmed from the abstract.) — [RePEc NBER 33152](https://ideas.repec.org/p/nbr/nberwo/33152.html); [ISB summary](https://www.isb.edu/faculty-and-research/research-directory/the-economics-of-buy-now-pay-later-a-merchant-s-perspective/)
- **deHaan, Kim, Lourie & Zhu, "Buy Now Pay (Pain?) Later" (Management Science, 2024):** banking data on 10.6M US consumers. Compared with non-users, new BNPL users' overdraft charges and credit-card interest and fees "rise sharply", which the authors read as overborrowing. They also use an instrument based on pre-BNPL shopping habits. — [INFORMS](https://pubsonline.informs.org/doi/fpi/10.1287/mnsc.2022.03266)
- Caveat (Atlanta Fed): neither the deHaan paper nor the related user-characteristics paper can establish which comes first, BNPL use or a tendency to overdraft. deHaan et al. concede that a coinciding shock (e.g., a layoff) is possible. — [Atlanta Fed, Take on Payments, 2023](https://www.atlantafed.org/research-and-data/publications/take-on-payments/2023/01/17/consumer-research-finds-an-association-between-bnpl-and-overdrafts)
- **Guttman-Kenney, Firth & Gathergood (J. Behavioral & Experimental Finance vol. 37, 2023, art. 100788):** UK credit-card transaction data show consumers paying BNPL instalments **with credit cards**. This is most common among **younger consumers** and residents of the most deprived areas. It moves an interest-free balance onto debt at about 20% APR with very long amortisation, which raises affordability concerns. — [arXiv 2201.01758](https://arxiv.org/abs/2201.01758v5); [Nottingham repository](https://nottingham-repository.worktribe.com/output/15926459/buy-now-pay-later-bnpl-on-your-credit-card)
- **Central Bank of Ireland, "Buy Now, Spend More, Pay Later" (Research Technical Paper 15/RT/25, 2025):** a randomised online shopping experiment with a nationally representative Irish sample and five arms (BNPL availability, use, information, and risk disclosure). Findings:
  - Participants spent **about 4.39% more with BNPL than with debit**.
  - Prior BNPL use inflated perceived available funds, making a discretionary purchase **22.2% more likely** (mental accounting).
  - Merely expecting future BNPL access raised current debit spending by **3.1%**.
  - No significant effect of BNPL *availability* on overall spending, possibly because of low take-up or few shopping rounds.

  Figures are from the search abstract; the PDF could not be fetched. — [CBI RTP 15/2025](https://www.centralbank.ie/docs/default-source/publications/research-technical-papers/rtp-15-2025-behavioural-mechanisms-of-bnpl.pdf?sfvrsn=9b816e1a_8); [RePEc](https://ideas.repec.org/p/cbi/wpaper/15-rt-25.html); [AEA RCT registry pre-registration](https://www.socialscienceregistry.org/versions/210531/docs/version/document)
- **ASIC Report 672 (Nov 2020), Australia:**
  - **21%** of surveyed BNPL users missed a payment in the previous 12 months.
  - Of those who missed a payment, **47% were aged 18–29**.
  - **67%** of transactions that incurred missed-payment fees were by consumers **under 35**.
  - Missed-payment fee revenue exceeded **A$43M**, up 38% year on year.
  - Transactions rose from 16.8M (2017–18) to 32.0M (2018–19).

  — [ASIC REP 672](https://download.asic.gov.au/media/5852803/rep672-published-16-november-2020-2.pdf); [ASIC media release 20-280MR](https://www.asic.gov.au/about-asic/news-centre/find-a-media-release/2020-releases/20-280mr-asic-releases-latest-data-on-buy-now-pay-later-industry)

### Inferences
- The mechanisms with the most support are (a) phantom or "flypaper" liquidity and mental accounting, where instalment framing makes the price feel smaller and funds feel available, and (b) instalment stacking, where the total exposure across plans is not salient. An intervention that targets these should **make the full cost and the stacked future instalments concrete against the user's own forecast cash**, rather than give generic warnings.
- PaySense's Engine 1 (shortfall forecast) already produces the counterfactual "your balance after this purchase's instalments" quantity, which is exactly what the CBI mechanism suggests is missing.

### Gaps
- The full text of Berg et al. (identification design) and of the CBI paper (sample size, standard errors, age heterogeneity) was not retrieved.
- A Sept-2026 survey, "Buy Now, Pay Later: Academic Insights and Open Policy Questions" (arXiv 2609.09323), turned up in search but could not be fetched. It may hold newer causal estimates. — [arXiv 2609.09323](https://arxiv.org/pdf/2609.09323)
- No ASIC data newer than REP 672 was retrieved in this session (e.g., ASIC's post-2024 regulation of BNPL as credit).

## 2. Interventions with measured effects at the point of a BNPL/credit decision

### Takeaway
The strongest *field* evidence for changing short-term-credit decisions is **cost salience in concrete money terms aimed at the adding-up error**: showing cumulative dollar cost cut payday borrowing by 11% (Bertrand & Morse). **Plain risk-disclosure boxes improve understanding but do not change BNPL use** (CBI 2025; UK experiment). Reminders and repayment nudges reduce the targeted fee (−14%) but can push costs elsewhere (+9% overdraft fees), or produce "semblance of success" nulls on actual debt. Opportunity-cost prompts and future-self framing have lab effects of moderate size that shrink in the field. Nudge effects overall are about 6× smaller at scale than in published papers.

### Cited Findings
**Meta-level calibration (read first)**
- **Mertens et al. (PNAS 2022):** a choice-architecture meta-analysis of 447 effect sizes from 212 publications. Pooled **d ≈ 0.43**, with "moderate publication bias". — [Maier et al. letter, PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9351501/); [Mertens et al. summary](https://ber.jcx.au/critical-reading/mertens-2022.html)
- **Maier, Bartoš, Stanley & Wagenmakers (PNAS 2022 letter):** after robust Bayesian meta-analysis (RoBMA) correction for publication bias, "no evidence for nudging" remains on average. Szaszi et al. called d = 0.43 "implausibly large". (Heterogeneity means some nudge classes may still work. Defaults were reported to hold up best in follow-ups, but that was not verified this session.) — [PMC9351501](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9351501/); [PsyPost summary](https://www.psypost.org/re-analysis-of-meta-analysis-reveals-no-evidence-for-nudging-once-accounting-for-publication-bias/)
- **DellaVigna & Linos (Econometrica 90(1), 2022), "RCTs to Scale":**
  - 126 RCTs with 23M people from two US Nudge Units. Average effect **1.4 pp (~8% relative)**, against **8.7 pp (~33.5%)** in academic journals.
  - Publication bias explains about 70% (and up to all) of the gap.
  - Forecasters overestimate Nudge Unit effects.

  — [NBER w27594](https://www.nber.org/papers/w27594); [Econometrica](https://econometricsociety.org/doi/10.3982/ECTA18709)

**Cost salience / adding up (strongest field evidence for short-term credit)**
- **Bertrand & Morse (J. Finance 66, 2011):** a field experiment with 1,441 payday borrowers at 77 stores, with treatment printed on the loan envelope. Showing the **adding-up of dollar fees** over repeated rollovers, compared with other credit products, **reduced payday take-up by about 11% over the next 4 months**. Showing the typical repayment profile had a smaller effect. — [J-PAL evaluation](https://www.povertyactionlab.org/evaluation/information-disclosure-cognitive-biases-and-payday-borrowing-united-states); [paper PDF via J-PAL](https://povertyactionlab.org/media/file-research-paper/information-disclosure-cognitive-biases-and-payday-borrowing)

**Risk disclosures for BNPL (null on behaviour)**
- **CBI 2025:** salient risk disclosures **improved understanding of BNPL risks but did not significantly change usage or spending**. — [CBI RTP 15/2025](https://www.centralbank.ie/docs/default-source/publications/research-technical-papers/rtp-15-2025-behavioural-mechanisms-of-bnpl.pdf?sfvrsn=9b816e1a_8)
- **UK online BNPL experiment (published as a public report on a ctfassets/BIT-style host, possibly commissioned by a UK body; publisher not confirmed):** a "Disclosure Box" and a "Disclosure Pop-up" with an extra decision point. The visible excerpt says neither changed the choice of BNPL. The excerpt was truncated; verify before citing. — [BNPL Experimental Research Public Report](https://assets.ctfassets.net/mfz4nbgura3g/14wX3p7vqOj3FNzUrlU5tl/ed64cdb7b950efcb82b1ed4b63f73240/Buy_20Now_20Pay_20Later_20Experimental_20Research_20Public_20Report.pdf)

**Reminders / just-in-time repayment nudges (side effects and nulls)**
- **Medina (Review of Financial Studies 34(5), 2021):** a randomised field experiment on a Brazilian financial-management platform. Payment reminders **cut credit-card late fees by 14%** but **raised overdraft fees by 9%**, concentrated among users with past overdrafts. — [RePEc](https://ideas.repec.org/a/oup/rfinst/v34y2021i5p2580-2607..html)
- **Adams, Guttman-Kenney, Hayes, Hunt, Laibson & Stewart:**
  - **Economica 2022:** two UK field experiments with **183,441** cardholders, using statement nudges and emails to people on autopay-the-minimum. **Precise null effects on long-run credit-card debt.** **96%** of survey respondents underestimated payoff time when paying only the minimum.
  - **FCA Occasional Paper 45 / AEJ: Policy 2025:** shrouding the minimum-autopay option cut "pay exactly the minimum" by **23%** at 6 months. It had **no effect on total repayments, spending, borrowing costs or net debt**, because people offset the higher automatic payment with smaller manual payments. Liquidity constraints are the best explanation.

  — [LSE eprint 115093](https://eprints.lse.ac.uk/115093/); [FCA OP 45](https://fca.org.uk/publications/occasional-papers/occasional-paper-no-45-semblance-success-nudging-consumers-pay-down-credit-card-debt)

**Opportunity-cost salience**
- **Frederick, Novemsky, Wang, Dhar & Nowlis (JCR 2009):** stating that unspent money could be used for other things cut willingness to buy a $14.99 DVD **from 75% to 55%**. Opportunity-cost cues lower purchase rates and raise the choice share of cheaper options. — [JCR 2009 PDF](https://spinup-000d1a-wp-offload-media.s3.amazonaws.com/faculty/wp-content/uploads/sites/48/2019/06/OpportunityCostNeglect.pdf)
- **Opportunity-cost-neglect meta-analysis (J. Economic Science Association, 2023):** the effect is real but "likely much smaller" than in Frederick et al. — [Springer](https://link.springer.com/article/10.1007/s40881-023-00134-6)
- **Chatterjee, Rai & Heath (2011)** on time-versus-money opportunity costs is listed in that meta-analysis with a 19.5% absolute change. It was not confirmed that the study used an hours-of-work price frame. — [Springer meta-analysis](https://link.springer.com/article/10.1007/s40881-023-00134-6)

**Future-self framing**
- **Hershfield et al. (J. Marketing Research 2011):** people shown an age-progressed avatar of themselves allocated **more than twice as much** to retirement (**d = 0.77** for dollar allocation, d = 0.74 for % of pay). This was a lab/VR study with a small n. The online follow-up raised allocations by about 33%. — [Hershfield, Goldstein et al. PDF](https://www.dangoldstein.com/papers/Hershfield_Goldstein_et_al_Increasing_Saving_Behavior_Age_Progressed_Renderings_Future_Self.pdf)
- **Christensen, Hershfield & Maglio:** 20 studies, including two field experiments. Starting from the future self and working back to the present beat the standard framing. In a Swedish fintech savings app (>6,500 clients), sign-up was **0.17% versus 0.04%**. The absolute rates are tiny. — [UCLA Anderson Review](https://anderson-review.ucla.edu/future-self-nudge-works-even-better-in-reverse)

**Friction / cooling-off**
- **Moser, Schoenebeck & Resnick (U. Michigan, impulse buying):** a **25-hour delay** lowered impulse purchases in an online experiment. A **10-minute** in-lab delay on Amazon was not significant; all participants kept shopping during the delay. Postponement beat outright prohibition. — [Moser et al. PDF](https://yardi.people.si.umich.edu/pubs/Schoenebeck_ImpulseBuying19.pdf)
- **"Dark patterns in online shopping" (Behavioural Public Policy):** a two-minute postponement, a reflection task and a distraction task all reduced purchase impulsivity within subjects. Between-subject effects varied. — [Cambridge BPP](https://www.cambridge.org/core/journals/behavioural-public-policy/article/dark-patterns-in-online-shopping-do-they-work-and-can-nudges-help-mitigate-impulse-buying/996B92402604A7E3D417ECBAE2C38362)

**Goal setting / precommitment in a fintech app**
- **Gargano & Rossi (J. Finance 79(3), 2024):** in a FinTech app, users given a goal-setting feature (randomised beta access, diff-in-diff) raised their savings rate, with no crowd-out of saving outside the app. The working paper's estimate roughly **doubled savings (~€345/yr)**. — [EconPapers](https://econpapers.repec.org/RePEc:bla:jfinan:v:79:y:2024:i:3:p:1931-1976); [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3579275)
- **Gargano & Rossi (carbon-calculator paper):** detailed transaction-level feedback was adopted but **did not change consumption**. Feedback alone is not enough. — [SSRN 4672645](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4672645)

**Price salience at checkout (non-BNPL field)**
- **Dertwinkel-Kalt, Köster & Sutter:** a field experiment with more than 34,000 online-cinema customers. A shrouded surcharge raised selection of the add-on, but drop-out rose when the total was revealed at checkout. The overall demand distribution did not depend on presentation. — [IZA DP 13798](https://www.iza.org/publications/dp/13798/to-buy-or-not-to-buy-price-salience-in-an-online-shopping-field-experiment)

### Inferences
- **Generic warnings fail; concrete, personal, adding-up arithmetic works.** Bertrand & Morse (a −11% behaviour change) and CBI (a disclosure that improved comprehension with no behaviour change) differ on exactly this: the effective treatment made the *cumulative money cost* concrete relative to alternatives, and the null treatments described *risk*. A PaySense card such as "With this plan, RM X of instalments are due across your next 6 weeks, on top of RM Y already committed. Your forecast balance on [due date] drops to RM Z (shortfall probability P%)" is the BNPL analogue of the Bertrand & Morse envelope, and it uses Engine 1 output.
- **Expected real-world size is small.** Use DellaVigna & Linos as the prior: perhaps a 1–3 pp change in take-up at scale, while lab/vignette effects of d ≈ 0.3–0.8 are plausible. A UAT will show the lab-type effect. Report it as such.
- **Watch for side effects.** Medina and the FCA OP 45 show that a nudge can move a cost rather than remove it. The app should track total committed instalments and overdraft/shortfall risk, not only whether the user tapped "skip BNPL".
- Opportunity-cost and "days of allowance" reframing are cheap add-ons with lab support (75%→55%) but a shrunken meta-analytic effect. They are best used as a secondary line inside the cost-salience card, not as the headline.

### Gaps
- No verified sources were retrieved this session for the following (all frequently cited; verify before use):
  - Gollwitzer & Sheeran's implementation-intentions meta-analysis (commonly cited as d ≈ 0.65, general goals, not finance-specific).
  - Ashraf, Karlan & Yin's SEED commitment savings (often cited as +81% savings balances).
  - Thaler & Benartzi's Save More Tomorrow.
  - Rung & Madden's episodic-future-thinking delay-discounting meta-analysis.
  - Hershfield's Mexico field study.
  - Social-norms comparisons applied to credit (no finance-specific RCT found).
  - Decoy effects in credit choice.
  - Defaults applied to BNPL (e.g., pay-in-full as the default).
- No RCT was found of a "cost in hours of work" reframe with a measured spending effect.
- No live-checkout randomised BNPL disclosure trial was found. The CBI and UK studies are hypothetical shopping tasks.

## 3. AI/chatbot-delivered financial advice or nudges

### Takeaway
No RCT was found (2020–2026) showing that a chatbot or LLM delivering *financial* advice changes savings, debt or BNPL behaviour more than static content. The closest evidence is from general behaviour change: short LLM conversations raise *readiness to change* and *behavioural intention*, not observed financial behaviour.

### Cited Findings
- **MIcha (Int. J. Human-Computer Studies, 2025):** a pre-registered RCT of a GPT-4 motivational-interviewing chatbot. Short conversations raised readiness to change, and outcomes depended on user interaction style (cooperative, reflective, pre-informed). Not finance. — [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S1071581925000710)
- **JMIR 2025 topic-based chatbot RCT:** significantly larger gains in behavioural intentions than a waitlist control (mental-health self-care). — [JMIR](https://www.jmir.org/2025/1/e70436)
- **JMIR mHealth 2025, CBT chatbot with Chinese university students (n = 100):** larger depression improvement among students with high financial stress. The outcome was mental health, not money. — [JMIR mHealth](https://mhealth.jmir.org/2025/1/e63806)
- A 2024 chatbot behaviour-change RCT (COVID protective behaviours, n = 59) reported small effects. — [J. Public Health Policy / PubMed](https://pubmed.ncbi.nlm.nih.gov/39060386)

### Inferences
- A claim that "an AI assistant changes BNPL behaviour" is **not yet evidence-backed**. The defensible framing is: the evidence-backed intervention is the cost and forecast salience, and the LLM is a *delivery channel* that narrates engine numbers. That fits D-47 (the LLM narrates; it never produces numbers) and is a testable hypothesis rather than a claim.
- An honest UAT can compare **static card versus card plus conversational explanation** and report whatever result appears. Without an existing RCT, even a small pilot is a novel contribution.

### Gaps
- No search covered robo-advisor nudge RCTs (e.g., D'Acunto, Prabhala & Rossi on robo-advising and diversification) or bank chatbots (Bank of America's Erica, Cleo). Searching "financial coaching chatbot trial" or "robo-advisor randomized" might find finance-specific evidence.

## 4. Counterfactual ("what would change the outcome") explanations and decision quality or trust

### Takeaway
User studies (mostly online, with vignettes) find that people prefer counterfactual explanations to factual ones. There is some evidence that counterfactuals improve users' understanding and prediction of AI decisions, but evidence that they beat *causal* explanations is mixed. A 2025 paper argues counterfactuals may not be the best recourse format.

### Cited Findings
- **Celar & Byrne (Memory & Cognition, 2023):** n = 731. Counterfactual explanations were judged better than factual ones. A follow-up reportedly found counterfactuals improved the accuracy of participants' own decisions compared with causal explanations. (Secondary citation.) — [ACM review of counterfactual explanations and recourse](https://dl.acm.org/doi/10.1145/3677119)
- **Warren, Byrne & Keane (2023):** n = 127. Counterfactuals raised trust and satisfaction compared with causal explanations. A separate summary of the same task design says counterfactuals improved prediction of AI decisions compared with no explanation, but **not** compared with causal explanations. **The secondary accounts conflict.** — [Springer UMUAI 2025 overview](https://link.springer.com/article/10.1007/s11257-025-09438-0); [ACM review](https://dl.acm.org/doi/10.1145/3677119)
- **FAccT 2024:** a 2×3 between-subjects study, N = 252, with simulated **loan applicants**. It compared point-based and region-based counterfactuals presented numerically, in natural language or visually, and measured subjective and objective understanding. — [FAccT 2024 paper](https://facctconference.org/static/papers24/facct24-112.pdf)
- **Upadhyay et al. (2025), "Counterfactual Explanations May Not Be the Best Algorithmic Recourse Approach".** — [Harvard PDF](https://iis.seas.harvard.edu/papers/upadhyay2025counterfactual.pdf); [ACM IUI 2025](https://dl.acm.org/doi/10.1145/3708359.3712095)

### Inferences
- PaySense's Engine 2 counterfactual search ("reduce the basket by RM X or wait N days and risk drops from High to Low") is supported for *understanding and trust*. The supporting studies are small, online and vignette-based, so present the counterfactual as an aid to understanding, not as proven to change behaviour.
- Pairing the counterfactual with the cost-salience card (Section 2) gives both "why" and "what to do". Implementation-intention logic (an if-then plan) would argue the actionable "what to do" part adds value, but that is not verified for finance.

### Gaps
- Effect sizes for Celar & Byrne and Warren et al. were not retrieved. No field (real-money) study of counterfactual explanations in credit was found.

## 5. Student financial literacy interventions in Malaysia/ASEAN

### Takeaway
No randomised intervention study with Malaysian university students and BNPL was found. The Malaysian literature is mostly cross-sectional surveys linking low financial literacy and attitudes to BNPL behaviour. Globally, financial education has a modest, real effect according to the RCT meta-analysis (Kaiser et al. 2022), against Fernandes et al.'s earlier "0.1% of variance" result.

### Cited Findings
- **Kaiser, Lusardi, Menkhoff & Urban (J. Financial Economics 145(2), 2022):** a meta-analysis of **76 RCTs** with more than 160,000 participants. Positive causal effects on knowledge and downstream behaviour, robust to publication-bias correction. Their estimate is at least three times Fernandes et al.'s. Decay is untested beyond about 6 months. (A knowledge effect of about 0.20 SD is reported secondhand; not verified.) — [RePEc JFE](https://ideas.repec.org/a/eee/jfinec/v145y2022i2p255-272.html); [VoxEU](https://cepr.org/voxeu/columns/financial-education-effective-and-efficient)
- **Fernandes, Lynch & Netemeyer (Management Science 2014):** interventions explain **0.1% of the variance** in financial behaviour. Effects decay to negligible about 20 months later, even for large programmes. — [VoxEU summary of both](https://cepr.org/voxeu/columns/financial-education-effective-and-efficient); [NBER w32355 review](https://www.nber.org/system/files/working_papers/w32355/w32355.pdf)
- **Malaysian student BNPL survey (150 active users):** perceived financial-management capability, attitude and perceived behavioural control significantly affected BNPL behaviour. The authors flag the lack of tests of behavioural interventions with longitudinal data as a gap. — [ResearchGate: BNPL and debt management among Malaysian university students](https://www.researchgate.net/publication/401246325_Buy_Now_Pay_Later_BNPL_Usage_and_Its_Impact_on_Debt_Management_Among_Malaysian_University_Students)
- **Peninsular Malaysia survey (n = 366):** most respondents were aware of BNPL bankruptcy risk, but only about half knew Malaysia's bankruptcy threshold. It also cites AKPK/Bernama 2024: **53,000 people under 30 hold about RM1.9B of debt** (a secondary citation). — [AIJBES 2025](https://gaexcellence.com/aijbes/article/view/5819)
- **Classroom intervention study (Cash Quiz programme):** the treatment group gained financial literacy. The sample may not be university students. — [Journal FKPT](https://journal.fkpt.org/index.php/gves/article/download/1680/732)

### Inferences
- The Malaysian gap the local literature names (no tested behavioural interventions) is one PaySense can claim to address, even with a pilot. Generic literacy modules are a weak lever. Just-in-time, decision-specific information is better aligned with both Kaiser et al. (effects concentrated near the decision; decay) and Bertrand & Morse.

### Gaps
- No AKPK programme evaluations and no Bank Negara Malaysia behavioural research were retrieved. No ASEAN RCT (e.g., Indonesia or Philippines student BNPL/paylater) was found. A targeted search of BNM's Financial Capability reports and the OJK (Indonesia) "paylater" research is recommended.

## 6. Best evidence-to-implementability ratio, and how to measure it in a 5–30-user UAT

### Takeaway
Build a **just-in-time "true cost and stacking" card** at the BNPL decision. It should show the cumulative instalments already committed plus this plan, the user's forecast balance on each due date and the shortfall probability (all from Engine 1 and Engine 2), and one actionable counterfactual ("wait until after allowance day" / "pay RM X less"). This combines the strongest field evidence (Bertrand & Morse's adding-up disclosure, −11% take-up) with the mechanism evidence on BNPL phantom liquidity (CBI +22% discretionary purchase, flypaper). It avoids the documented null of generic risk warnings, and every number traces to existing engines (no fabricated numbers). Measure it with a within-subject, counterbalanced vignette A/B. With 30 users, only effects of about d ≥ 0.5 are detectable.

### Cited Findings
- Adding-up disclosure: −11% payday take-up over 4 months (field RCT, 1,441 borrowers). — [J-PAL](https://www.povertyactionlab.org/evaluation/information-disclosure-cognitive-biases-and-payday-borrowing-united-states)
- Generic BNPL risk disclosure improves comprehension, not usage. — [CBI RTP 15/2025](https://www.centralbank.ie/docs/default-source/publications/research-technical-papers/rtp-15-2025-behavioural-mechanisms-of-bnpl.pdf?sfvrsn=9b816e1a_8)
- BNPL inflates perceived available funds (22.2% higher chance of a discretionary purchase). — [CBI RTP 15/2025](https://www.centralbank.ie/docs/default-source/publications/research-technical-papers/rtp-15-2025-behavioural-mechanisms-of-bnpl.pdf?sfvrsn=9b816e1a_8)
- 96% of cardholders underestimate payoff time, a misperception that concrete arithmetic targets. — [LSE eprint 115093](https://eprints.lse.ac.uk/115093/)
- Lab-to-field shrinkage: 8.7 pp in journals versus 1.4 pp at scale. — [NBER w27594](https://www.nber.org/papers/w27594)
- Delay effects depend on the delay being long enough: 25 h worked, 10 min did not. — [Moser et al.](https://yardi.people.si.umich.edu/pubs/Schoenebeck_ImpulseBuying19.pdf)
- Power calculation (computed locally with scipy, paired t-test, two-sided α = 0.05, 80% power). Minimum detectable within-subject effect:

  | n | Minimum detectable d |
  |---|---|
  | 5 | 1.69 |
  | 10 | 1.00 |
  | 15 | 0.78 |
  | 20 | 0.67 |
  | 30 | 0.53 |

  (Own calculation; no external source.)

### Inferences
**Ranking (evidence × implementability in a hackathon)**
1. **Cost and stacking salience tied to a personal forecast.** Strongest field analogue (Bertrand & Morse). Directly fixes the BNPL mechanism (phantom liquidity, stacking). Uses existing Engine 1 and Engine 2 output. Small UI work.
2. **Actionable counterfactual ("what would make this safe").** Supported for understanding and trust (Celar & Byrne; FAccT 2024 loan study). The Engine 2 counterfactual already exists. Weak evidence on behaviour.
3. **Opportunity-cost / "days of allowance" reframe.** Cheap. Lab effect 75%→55% that shrinks in meta-analysis. Use as one line on card 1.
4. **Cooling-off / "decide after payday" postponement.** Evidence is mixed: short delays fail. Implement as an optional "remind me in 24 h / after allowance day" precommitment, which needs no write tool beyond a user-confirmed pending action (D-48).
5. **Future-self framing.** Lab d ≈ 0.77, field absolute effects tiny. Harder to do credibly.
6. **Chatbot delivery.** No finance RCT evidence. Test it, but don't claim it.
7. **Social norms, decoys, defaults.** Unverified for BNPL. Defaults are powerful in general, but the app does not control the merchant checkout.

**UAT design (5–30 users)**
- **Design:** within-subject, counterbalanced (AB/BA) vignette task. Each user sees about 6–8 realistic BNPL purchase scenarios, priced in sen and drawn from their own seeded persona ledger. Half are shown with the control (standard instalment view: "4 × RM 37.50") and half with the treatment card (stacked dues, forecast balance on due dates, shortfall probability, one counterfactual). Randomise which scenarios get which condition, so that scenario difficulty is balanced.
- **Primary outcome:** proportion of "affordable-flagged-risky" purchases the user chooses to BNPL now, compared with wait or skip. Analyse with a McNemar test or a mixed-effects logistic regression (user random intercept), and report the paired risk difference with a 95% CI.
- **Secondary outcomes:**
  - comprehension: correctly state the total due over the next 6 weeks, and the balance on the due date (objective accuracy, a CBI-style measure);
  - decision confidence;
  - trust or understanding of the score (short scale);
  - time to decide.
- **Optional third arm (n ≥ 20):** the same card with an LLM narration, versus the static card, to test the "conversational versus static" question honestly.
- **Reporting:** report the effect with its CI even if it is null (hard constraint 5). Frame the result as a lab/vignette effect and cite DellaVigna & Linos to state that real-world effects are expected to be several times smaller. At n = 30, a d ≈ 0.5 change is detectable. With n < 10, treat it as qualitative usability evidence, not an effect estimate.
- **Pre-register** the hypothesis and primary outcome in the repo (a plan doc) before running. This is cheap credibility.

### Gaps
- No published study tests a *personal-forecast-based* BNPL affordability card. PaySense would be testing an extension of Bertrand & Morse, not replicating it. Say so in the pitch.
- Vignette choices may not predict real BNPL behaviour (hypothetical bias). The CBI and UK studies have the same limitation.
