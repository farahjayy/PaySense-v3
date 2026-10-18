# Hackathon judging and winners: FinTechathon (Shenzhen) and AI personal-finance tracks

Scope: how the Shenzhen FinTechathon and similar fintech competitions are judged, what winners and strong entrants built, and the patterns that set winners apart. The focus is the International Track, Topic A (Personal Finance Assistant).

Method note: direct page fetches to the official site (`fintechathon.g-ican.com`), IEEE, InfoQ, Baidu and the aggregators were blocked by this environment's network policy. Findings come from (1) search-engine summaries of those pages, (2) a markdown conversion of the official rules PDF ("PBCSF Appendix 2"), and (3) public GitHub repositories of other 2026 entrants who transcribed the rules. Competitor repos are cited as **what rival teams claim about themselves**, not as verified facts. Per CLAUDE.md rule 7, competition dates and calendars are left out on purpose; stages are given in order only.

---

## 1. Published judging criteria and weights

### Takeaway
The 2026 International Track has a published, uniform rubric: **task completion 40%, security and compliance 30%, innovation and interaction 30%**, plus a capped 0–5 bonus. The official site's rules page adds sub-criteria that matter a great deal. Security is judged against four named attack classes (induced transfers, data extraction, privilege escalation, prompt injection), and "serious security failures trigger substantial deductions". Innovation and interaction covers novelty, real-world value, dialogue efficiency, clarification, correction and fallback. Earlier FinTechathon editions weighted technical implementation highest (50% in 2021).

### Cited Findings
**2026 International Track (the competition PaySense is entering)**
- Theme: "AI as a Financial Participant": "each team designs and builds an AI agent capable of completing real tasks in a financial scenario". Choose one of six topics. — [PBCSF Appendix 2, rules PDF (ITS mirror)](https://www.its.ac.id/international/wp-content/uploads/sites/66/2026/10/PBCSF-Appendix-2-Problem-Description-and-Competition-Rules-for-International-Track.pdf); markdown conversion at [beingmushfiq/CenterPoint-ProERP](https://github.com/beingmushfiq/CenterPoint-ProERP/blob/HEAD/PBCSF%20Appendix%202-Problem%20Description%20and%20Competition%20Rules%20for%20International%20Track.md)
- Topic A text, verbatim: "Personal Finance Assistant — An intelligent assistant for individual users, capable of smart budgeting, bill analysis, and spending insights, delivering actionable recommendations based on the user's income and expenses." — [Appendix 2 (markdown)](https://github.com/beingmushfiq/CenterPoint-ProERP/blob/HEAD/PBCSF%20Appendix%202-Problem%20Description%20and%20Competition%20Rules%20for%20International%20Track.md)
- "All six topics share the same core capability requirements and scoring criteria; choosing the on-chain topic does not affect scoring": Task completion 40% · Security & compliance 30% · Innovation & interaction 30% · "Challenge bonus (on-chain exploration): 0–5 points". — [Appendix 2](https://github.com/beingmushfiq/CenterPoint-ProERP/blob/HEAD/PBCSF%20Appendix%202-Problem%20Description%20and%20Competition%20Rules%20for%20International%20Track.md); same table in a docx transcription at [sanyuktaphanse/lifeline rules.md](https://github.com/sanyuktaphanse/lifeline/blob/HEAD/docs/hackathon/rules.md)
- **Sub-criteria from the official website's rules page** (`#/rule`, read by the team in English and Chinese, "The Chinese text prevails"):
  - task completion 40%;
  - security & compliance 30%: "defence against induced transfers, data extraction, privilege escalation and prompt injection; 'serious security failures trigger substantial deductions'";
  - innovation & interaction 30%: "novelty, real-world value, dialogue efficiency, clarification, correction and fallback";
  - "a capped 0–5 bonus for advanced topics or real-world deployment".
  — [Brieuclerouxtardif/leash docs/SUBMISSION.md](https://github.com/Brieuclerouxtardif/leash/blob/HEAD/docs/SUBMISSION.md). Independently corroborated, with the same four attack classes and the same six interaction words, by [ahammadshawki8/guardian Guardian.md §18.1](https://github.com/ahammadshawki8/guardian/blob/HEAD/Guardian.md).
- Brief wording quoted by a second team: "deliver a working financial Agent that demonstrates intent understanding, task planning, safe execution, user control and measurable value." — [guardian Guardian.md §18.1](https://github.com/ahammadshawki8/guardian/blob/HEAD/Guardian.md)
- Deliverables, from Appendix 2:
  1. technical documentation (architecture, core algorithms, security design);
  2. deck for a final presentation of 10 minutes or less;
  3. demo video of 5 minutes or less;
  4. source code with README, GitHub link, deployment instructions and test cases;
  5. security self-assessment report ("permission-tier implementation and known-risk list");
  6. execution evidence ("for non-on-chain topics: simulated-account/sandbox operation logs and demo video").
  — [Appendix 2](https://github.com/beingmushfiq/CenterPoint-ProERP/blob/HEAD/PBCSF%20Appendix%202-Problem%20Description%20and%20Competition%20Rules%20for%20International%20Track.md)
- **Conflict on what is required:** Appendix 2 and the docx call the demo video "optional". The website rules page (per the leash team) lists the demo video as **required** and lists source code, security self-assessment and execution evidence as **optional**. — [Appendix 2](https://github.com/beingmushfiq/CenterPoint-ProERP/blob/HEAD/PBCSF%20Appendix%202-Problem%20Description%20and%20Competition%20Rules%20for%20International%20Track.md) vs [leash SUBMISSION.md](https://github.com/Brieuclerouxtardif/leash/blob/HEAD/docs/SUBMISSION.md). The guardian team's response was "submit all six". — [Guardian.md §15](https://github.com/ahammadshawki8/guardian/blob/HEAD/Guardian.md)
- Review process, in order: compliance screening, then online review "by a panel of WeBank industry experts and university scholars", then finalists announced (10 per track, per guardian), then a WeBank HQ visit, an English on-site defence and the awards in Shenzhen. At least one member must attend in person. — [Appendix 2](https://github.com/beingmushfiq/CenterPoint-ProERP/blob/HEAD/PBCSF%20Appendix%202-Problem%20Description%20and%20Competition%20Rules%20for%20International%20Track.md); [guardian Guardian.md](https://github.com/ahammadshawki8/guardian/blob/HEAD/Guardian.md); [leash SUBMISSION.md](https://github.com/Brieuclerouxtardif/leash/blob/HEAD/docs/SUBMISSION.md)
- Prizes (International Track pool RMB 250,000): First RMB 100,000; Second RMB 80,000; Third RMB 50,000; **Best Innovation Award RMB 20,000**; several Excellence Awards. Outstanding teams get fast-track WeBank interviews. — [Appendix 2](https://github.com/beingmushfiq/CenterPoint-ProERP/blob/HEAD/PBCSF%20Appendix%202-Problem%20Description%20and%20Competition%20Rules%20for%20International%20Track.md)
- Hosts and advisers (team-compiled): Shenzhen University–WeBank Institute of FinTech, with strategic guidance from the Shenzhen Municipal Local Financial Administration. Technical advisers include CCF TC Digital Finance, the Tsinghua Institute of Financial Technology and the IEEE CIS Singapore and Shenzhen chapters. Academic advisers include Wang Shouyang, **Qiang Yang (WeBank Chief AI Adviser)**, Dacheng Xiu and Wolfgang Karl Härdle. — [guardian Guardian.md §18.1](https://github.com/ahammadshawki8/guardian/blob/HEAD/Guardian.md). The rules PDF itself is branded "PBCSF" (Tsinghua PBC School of Finance) and gives a pbcsf.tsinghua.edu.cn contact. — [Appendix 2](https://github.com/beingmushfiq/CenterPoint-ProERP/blob/HEAD/PBCSF%20Appendix%202-Problem%20Description%20and%20Competition%20Rules%20for%20International%20Track.md)
- 2026 **Domestic** Track (not the International Track): per a Baidu Baike entry, entries must meet "core technical requirements such as permission hierarchy mechanisms, hallucination prevention and injection defense, intent understanding, and task planning". Evaluation uses "automated evaluation and expert blind review" in a dual-track screening. The same source says the International Track keeps the theme and the Agent Wallet direction and adds five directions. — [Baidu Baike (via search summary)](https://baike.baidu.com/en/item/The%208th%20FinTechathon%20Shenzhen%20International%20FinTech%20Competition%202026/5383419). The search tool flagged this page's dates as unreliable.

**Earlier FinTechathon / WeBank university competition weightings**
- 2019 (first WeBank FinTechathon): judged on "product completeness, commercial value, innovation" (no weights published). — [GeekPark](https://www.geekpark.net/news/245456) (via search summary)
- 2021 (third edition): **technical implementation 50%** ("actual degree of completion … technical ability and task-handling effect"), product design and innovation 30%, commercial value 20%. An expert committee approves the results. — [CSDN 2021 announcement](https://blog.csdn.net/dQCFKyQDXYm3F8rB0/article/details/120465201); [FinTechathon 2021 page](https://fintech.webank.com/fintechathon/campus2021/) (via search summary)
- 2023 Shenzhen International FinTech Competition, **product-manager track**: completeness 40% and innovation 40%. Completeness covers "feasibility analysis, solution design documents, code implementation and test reports" and "technical complexity and implementation completeness". — [InfoQ](https://www.infoq.cn/article/njklsrobg4rfmaaydu13); [Tencent News](https://news.qq.com/rain/a/20231108A04TJ300) (via search summary)

**Comparable non-FinTechathon rubrics**
- Money20/20 Hackathon (2018): Simplicity, Creativity, Impact and Design, each scored out of 5, with judges' scores averaged; that year's theme was financial health and inclusion. — [Forbes](https://www.forbes.com/sites/tomgroenfeldt/2018/10/30/money-2020-hackathon-aimed-at-financial-health-and-inclusion/) (via search summary)
- "Hack the Concrete Jungle: Money 20/20 Las Vegas" (Devpost; year not shown): Innovation 30%, Execution 25%, Impact 25% (the remaining weight was not in the snippet). — [Devpost](https://hacktheconcretejungle-lv.devpost.com/) (via search summary)
- A published hackathon judging doc says the demo matters most and that judges do not grade pitch quality or idea quality on their own. — [DiamondHacks judging criteria](https://github.com/annaowens/DiamondHacks21/blob/master/Judging%20Criteria.md) (via search summary)

### Inferences
- The 40/30/30 split already in `refdocs/fintechathon-2026/work-packages.md` is **confirmed by the rules PDF**. The sub-criteria (four attack classes; clarification, correction and fallback; "substantial deductions") are **not** in the PDF. They come from the website rules page, as reported by two independent teams. Treat them as highly likely official.
- "Serious security failures trigger substantial deductions" makes security asymmetric: one visible failure in front of judges can cost more than any single feature earns.
- The rubric names **dialogue behaviours** (clarification, correction, fallback, dialogue efficiency) explicitly. A demo should show each one on camera, not only describe them in docs.
- The Best Innovation Award is a separate, single prize. A highly original but less complete entry has its own route to a prize.
- Historically (2021), "actual degree of completion" carried the most weight. The 2026 rubric keeps that emphasis through the 40% task-completion criterion.

### Gaps
- No official per-sub-criterion point split (for example, how the 30% security is divided among the four attack classes).
- Could not read the official website rules page directly (blocked). The sub-criteria rest on two competitor transcriptions.
- No published judge names for the 2026 International Track panel beyond "WeBank industry experts and university scholars".
- HKUST/HKU fintech competitions and Visa/Mastercard student challenges: no rubric found within this session's search budget.

---

## 2. What winning and finalist projects built (2019–2026)

### Takeaway
Past FinTechathon AI-track winners were technically deep and tied to WeBank's own technology. Federated learning on WeBank's FATE platform recurs (car-insurance pricing, tumour diagnosis, vertical-federated credit assessment). The 2025 AI champion was a multi-agent LLM system that runs an end-to-end financial workflow. No 2026 winners exist yet. The visible 2026 Topic A and adjacent field has converged on one design pattern: "the model proposes, deterministic code decides", with permission tiers and scripted attack suites.

### Cited Findings
**FinTechathon past winners (WeBank / Shenzhen University family)**
- 2019 first prize: horizontal federated learning for car-insurance pricing from in-vehicle driving-behaviour data. — [InfoQ](https://www.infoq.cn/article/njklsrobg4rfmaaydu13) (via search summary)
- 2020: AI track first place TAN's fellow (Beijing Institute of Technology). Blockchain track first place 紫荆路航空团 (South China Normal University), with a "time bank" blockchain public-welfare platform. — [weiyangx](https://www.weiyangx.com/374338.html) (via search summary)
- 2021 first prize: a mental-health prediction and monitoring system combining users' text, images and social-media data. — [InfoQ](https://www.infoq.cn/article/njklsrobg4rfmaaydu13) (via search summary)
- 2022 first prize: a perception system for real-person experience using horizontal federated learning across several people's data. — [InfoQ](https://www.infoq.cn/article/njklsrobg4rfmaaydu13) (via search summary)
- 2023 AI track first prize: **OncoFed, a FATE-based tumour-diagnosis project** (team Aa100K, Nanjing University and Xidian University). The AI-track brief that year was to build on FATE with vertical or horizontal federated learning or a "federated large model". — [Shenzhen University news](https://www.szu.edu.cn/info/1161/18428.htm) (via search summary)
- 2024: 2,539 students, 534 teams, 321 submissions; three tracks (AI, blockchain, product manager), 10 finalists each; RMB 690k in prizes. Zhejiang University of Finance and Economics (ZUFE) had two AI-track finalists, Dream Weavers and Eureka, and one won the AI-track title. Eureka's work was **"One-shot SSVFATE: a personalised self-supervised vertical federated credit-assessment system"**. Which team won is not stated explicitly. Judges came from Xiamen University, Guangdong University of Finance and Economics, Shenzhen University and WeBank. — [ZUFE news](https://info.zufe.edu.cn/info/1074/18035.htm); [Tencent News, top-10 list](https://news.qq.com/rain/a/20241128A07I3500); [FinTechathon past 2024 page](https://fintechathon.csdn.net/past/2024); [SZU news](https://news.szu.edu.cn/info/1003/13028.htm) (via search summaries)
- 2025: 1,709 students, 372 teams, 270 universities; AI and data-analysis tracks; RMB 500k pool, first prize RMB 100k. The **AI-track champion was 《灵操盘》 ("Ling Caopan")**, a zero-code quantitative-trading engine whose core is a "finance-knowledge-driven large model plus multi-agent collaborative architecture" covering the full chain from data processing to live execution. The data-analysis champion was an anti-money-laundering fraud-detection project. One data-analysis topic was "stability of credit-customer risk scores". — [Dutenews](https://m.dutenews.com/n/article/10315760); [China.com](https://m.tech.china.com/redian/2025/1209/122025_1778234.html); [showapi summary](https://www.showapi.com/news/article/68f2288f4ddd79d13501416f) (via search summaries)
- 2025 Best Creative: "Echopolis, an LLM digital-twin financial sandbox (Nanjing University)". 灵操盘 is attributed to HKUST-GZ. — **only** from a competitor's notes ([guardian Guardian.md §18.1](https://github.com/ahammadshawki8/guardian/blob/HEAD/Guardian.md)). A Chinese-language search found no confirmation.

**Visible 2026 Topic A entrants (rival self-descriptions, unjudged)**
- **FundBun** (Topic A; Universitas Gadjah Mada and Universitas Airlangga, Indonesia): "Dream Mirror" restates overspending as the dream item it cost you. Other features: tripwires; budgets with a "Should I buy it?" check in hours of work and days of goal delay; bill analysis plus "Bill X-ray" of pasted bills with prompt-injection detection; anomaly insights (modified z-score); a multi-step agent planner (DAG) with clarification, correction and interrupt; a five-tier deterministic permission engine; and a "Glass Box" desktop panel showing the live agent trace, policy decisions and audit tail. It has an offline TF-IDF intent engine plus an optional LLM gateway (Anthropic default, OpenAI-compatible for DeepSeek/Qwen). Its measured claims are "45/45 scripted scenarios · 231/231 assertions · 24/24 attacks blocked (¥0 moved) · 0% false refusals · 44/44 audit chains intact, tampering detected · byte-identical reruns" and "2,700+ tests". It has a hosted live demo (persona URLs, demo PIN) and a 4:47 video. Scenario suites map to the rubric: A task completion; B safe execution and user control; C the four attack classes plus hallucination, tampering, rate abuse and a circuit breaker; D privacy. — [odripads/fundbun README](https://github.com/odripads/fundbun)
- **DialectGuard** (Topic A; Malaysia): pays elderly users' bills "in her own dialect" (Cantonese, Hokkien, Manglish) inside a chat app and "can't be talked into paying a scammer". Its design: the AI is not on the payment path (fixed rules plus a weighted risk score, template-only replies); approvals are ECDSA-signed records with a nonce and expiry; a family member approves "Review" cases; and every transaction stores a decision record that doubles as execution evidence. — [25006675-png/Teman PROPOSAL.md](https://github.com/25006675-png/Teman/blob/HEAD/PROPOSAL.md)
- **Monetra AI** (Topic A): FastAPI with deterministic Python services; Gemini "explains verified values rather than determining balances"; CSV import, budgets, a month-end forecast and risk signals, upcoming bills, a read-only what-if purchase simulator. — [RR0327/monetra-ai](https://github.com/RR0327/monetra-ai)
- **Monara** (Topic A; Indonesia, IDR): a Next.js PWA with Supabase RLS, Gmail receipt ingestion (Composio) and an authenticated chat bridge to a Cloudflare Agent runtime. — [ZoeMohamed/Monara](https://github.com/ZoeMohamed/Monara)

**Strong adjacent 2026 entrants (other topics; useful for spotting patterns)**
- **Sathi** (Topic C, Bangladesh → China): "Judge mode", reachable from Settings or one script, runs "20 of 20 scripted tasks … each in a fresh sandbox". Results: task completion 9/9; security 7/7, including a "compromised-AI drill: a malicious model drives the agent's tools and moves no money"; interaction 4/4. Each task shows its steps, checks, value and proving log entry. Other features: a 10-step "story mode", real published bank rates and fees with assumptions labelled, quoted student interviews, and passkey-signed mandates spoken in Bangla. — [Tasrif-Ahmed-Mohsin/finbuddy](https://github.com/Tasrif-Ahmed-Mohsin/finbuddy)
- **FlowGuard Sentinel** (Topic E): the owner approves an exact payload; a policy engine re-checks it; an "independent verifier checks what actually changed"; and an "Evaluation lab" shows "matched gated/ungated tests". — [daudibrahimhasan/FlowGuard-Sentinel](https://github.com/daudibrahimhasan/FlowGuard-Sentinel)
- **Lifeline** (Topic C): a Python mandate engine (rules R01–R14, tiers); a hash-chained ledger with a **FISCO BCOS anchor** (FISCO BCOS is WeBank's open-source consortium blockchain); `pytest` 1,642 tests; `make evidence` reporting "58 passed … stranger runs: 16 passed"; and an open-items list that admits gaps (for example, nothing in code checks the "no investment advice" rule). — [sanyuktaphanse/lifeline](https://github.com/sanyuktaphanse/lifeline)
- **SME copilot** (Topic E): its README maps each rubric line to features: "Three-Tier Security Gate…, WebAuthn physical biometric 2FA, Presidio PII redaction, and Truth-in-Lending APR disclosures". — [SamJU25/F-SME-Finance-Copilot](https://github.com/SamJU25/F-SME-Finance-Copilot)
- A Topic E entry publishes a table mapping each of the four attack classes to "what stops it" and to named evaluation-task IDs (for example, induced transfer → maker-checker with fresh authenticator codes → ADV-25, ADV-14 …). — [tanhongsheng050204-code README](https://github.com/tanhongsheng050204-code/2026-SHENZHEN-FINTECHATHON-INTERNATIONAL-TRACK)
- **Guardian** (Topic F): its one-sentence hook is "Scammers tricked our AI wallet on camera, and the money stayed put". It has a public red-team scoreboard ("attacks run · AI fooled · money lost $0"), a Jailbreak Mode switch in the demo, and a planned adaptive LLM red-teamer reported separately from the fixed suite. — [guardian Guardian.md](https://github.com/ahammadshawki8/guardian/blob/HEAD/Guardian.md)

**Other recent AI personal-finance wins**
- Money20/20 USA Global Money Awards 2025 (an awards programme, not a hackathon): Cleo AI won a Grand Prix for a personal-finance AI coach. The jury cited financial inclusion, AI use and a scalable platform. — [Money20/20 press release](https://www.money2020.com/awards/winners-press-release) (via search summary)
- Google GDC Fintech AI Hackathon 2025 (with nsave): first place went to "Budgetly" (Ain Shams University), a personal-finance app giving tailored advice. 87 teams entered, with a top 12 before the final round. — [Ain Shams University news](https://asu.edu.eg/8679/news) (via search summary)

### Inferences
- **Past winners won on technical depth and sponsor-tech alignment, not UI.** Four of the documented AI-track winners (2019, 2022, 2023, and probably 2024) used federated learning, mostly on WeBank's FATE. Qiang Yang, a federated-learning pioneer, is listed as an academic adviser. Privacy-preserving computation is the house signature.
- The 2025 champion's description ("full chain from data processing to live execution", "multi-agent") fits the 2026 theme of an agent that completes real tasks. Judges reward end-to-end execution over a single model.
- In the visible 2026 field, the following are **table stakes, not differentiators**: "the model proposes, deterministic code decides"; permission tiers; prompt-injection tests on pasted text; confirm-before-write; audit logs. FundBun and DialectGuard, both Topic A, already have all of them, plus measured attack scoreboards.
- **Direct overlap for PaySense:** Monetra AI has the same architecture (FastAPI with deterministic services, Gemini explains verified numbers, a what-if purchase simulator). FundBun has a "Should I buy it?" affordability check. PaySense's distinctive assets are a trained and benchmarked forecasting and risk-classification pipeline (ARIMA/Prophet/LSTM; RF/XGBoost/LightGBM with SHAP), the BNPL-specific domain (stacked instalments, provider rules) and the student focus. None of the visible Topic A rivals claims an evaluated ML engine with benchmarks.
- DialectGuard (Malaysia) also targets a Malaysian vulnerable group. The Malaysian context alone will not stand out; the BNPL and student-credit angle has to carry it.

### Gaps
- No public list of 2026 International Track finalists or winners exists yet; the International Track is new in 2026, so there is no prior International winner.
- I could not confirm the Echopolis Best-Creative claim or the exact 2024 AI-track winner.
- I found no FinTechathon winner write-ups or demo videos describing *how* past winners demoed.
- Only a handful of the visible rivals' repos were read; many entrants keep private repos.

---

## 3. What judges say they look for

### Takeaway
There are no published judge interviews for the 2026 International Track. The rubric wording, the panel make-up (WeBank industry experts plus academics) and past criteria point to the same priorities: verifiable completion of real tasks, defence against named attack classes, visible user control, and measurable value. Rival teams' own judge-reading converges on "make safety visible on screen" and "show one complete workflow".

### Cited Findings
- The panel is "WeBank industry experts and university scholars". — [Appendix 2](https://github.com/beingmushfiq/CenterPoint-ProERP/blob/HEAD/PBCSF%20Appendix%202-Problem%20Description%20and%20Competition%20Rules%20for%20International%20Track.md)
- The brief asks for "intent understanding, task planning, safe execution, user control and measurable value". — [guardian Guardian.md](https://github.com/ahammadshawki8/guardian/blob/HEAD/Guardian.md)
- 2021 judging stressed the "actual degree of completion" and "task-handling effect". — [CSDN 2021](https://blog.csdn.net/dQCFKyQDXYm3F8rB0/article/details/120465201) (via search summary)
- The 2023 product track counted feasibility analysis, design docs, code and **test reports** toward completeness. — [InfoQ](https://www.infoq.cn/article/njklsrobg4rfmaaydu13) (via search summary)
- WeBank's public positioning stresses technology plus inclusion (MSMEs and the general public), "compliant operation and rigorous risk control". A rival suggests the headline "From digital financial access to digital financial agency". — [ZoeMohamed/Monara judge research](https://github.com/ZoeMohamed/Monara/blob/HEAD/deck/research/sea-market-competition-compliance.md) (rival's synthesis of WeBank pages)
- Rival advice drawn from the rubric: "For task completion, show one complete workflow rather than many disconnected features". "For security and compliance, make the safety decisions visible on-screen. Do not bury them in architecture slides." "The innovation is not 'we built a chatbot.'" — [Monara judge research](https://github.com/ZoeMohamed/Monara/blob/HEAD/deck/research/sea-market-competition-compliance.md)
- Audience framing from another entrant: "Audience: bankers and academics. Lead with limits, explanations and audit, not with UI polish." — [gabi200/runway docs/demo-script.md](https://github.com/gabi200/runway/blob/HEAD/docs/demo-script.md)
- Money20/20 jury language (Cleo AI): "financial inclusion, AI use, scalable platform". — [Money20/20](https://www.money2020.com/awards/winners-press-release) (via search summary)
- General hackathon guidance (secondary blogs, uneven reliability): agentic, RAG or multimodal builds aimed at a specific problem outscore a generic app with an LLM attached; a working product beats an ambitious unfinished one; live data is more credible than mocked data. — [HackerEarth](https://www.hackerearth.com/blog/hackathon-ideas); [Lessons from Winning Five Hackathons](https://sustained.substack.com/p/lessons-from-winning-five-hackathons) (via search summary)

### Inferences
- With bankers and academics judging, **rigour signals** (reproducible evaluation, benchmarks, honest limits, known-risk lists) are likely to score better than polish. This matches PaySense's existing "no fabricated numbers" and "benchmarks always included" constraints.
- "Measurable value" in the brief suggests judges want a number showing the user is better off (for example, shortfalls avoided, cost of credit avoided, users who changed decisions), not only system metrics.
- The English on-site defence means judges will probe "why AI here?" and "isn't this just X?". Guardian's prepared Q&A shows the expected questions.

### Gaps
- No direct quotes from 2026 judges or from past FinTechathon judges about what tipped decisions.
- No organiser blog post or post-mortem on judging.

---

## 4. Recurring "wow" demo mechanics

### Takeaway
Across the strongest visible entrants, the recurring mechanics are:
- a judge-runnable, one-command or in-app scripted task suite with pass counts;
- a live attack on camera that visibly fails (money stays put);
- a glass-box trace of agent steps and policy decisions;
- signed or confirmed user approvals of an exact payload;
- tamper-evident audit chains;
- a vivid, relatable reframe of the user's data.

### Cited Findings
- **Judge mode / one-command evidence:** Sathi's "Settings → Judge mode" with 20/20 tasks, each showing "steps, checks, value and the log entry that proves it" ([finbuddy](https://github.com/Tasrif-Ahmed-Mohsin/finbuddy)). FundBun's `npm run evidence` replays all scenarios with byte-identical reruns ([fundbun](https://github.com/odripads/fundbun)). Lifeline's `make evidence` includes "stranger runs" ([lifeline](https://github.com/sanyuktaphanse/lifeline)).
- **Attack on camera, nothing moves:** "Scammers tricked our AI wallet on camera, and the money stayed put", plus a red-team scoreboard (attacks run / AI fooled / money lost) and a Jailbreak Mode toggle ([guardian](https://github.com/ahammadshawki8/guardian/blob/HEAD/Guardian.md)). Sathi's "compromised-AI drill" ([finbuddy](https://github.com/Tasrif-Ahmed-Mohsin/finbuddy)). FundBun's "24/24 attacks blocked (¥0 moved)" ([fundbun](https://github.com/odripads/fundbun)).
- **Fooled versus harmed, measured separately:** Guardian's "AI fooled" against "money lost $0" ([guardian](https://github.com/ahammadshawki8/guardian/blob/HEAD/Guardian.md)). FlowGuard's "matched gated/ungated tests" ([FlowGuard](https://github.com/daudibrahimhasan/FlowGuard-Sentinel)).
- **Glass box:** FundBun's desktop "Glass Box" (live agent trace, policy decisions, audit tail, sandbox controls) beside a phone-sized app ([fundbun](https://github.com/odripads/fundbun)). Guardian's three-panel layout: phone chat, vault rules, live chain feed ([guardian](https://github.com/ahammadshawki8/guardian/blob/HEAD/Guardian.md)).
- **Tamper-evident audit:** FundBun reports 44/44 audit chains intact with tampering detected. Lifeline uses a hash-chained ledger anchored to FISCO BCOS. — [fundbun](https://github.com/odripads/fundbun); [lifeline](https://github.com/sanyuktaphanse/lifeline)
- **Strong user-control primitives:** passkey or WebAuthn signatures (Sathi, SME copilot); ECDSA-signed approvals with nonce and expiry (DialectGuard); a trusted family approver (DialectGuard, Sathi, Guardian); a kill switch, "Freeze Bun" and undo (FundBun). — sources as cited in §2
- **Vivid reframing of money:** FundBun's "You could've gotten a Birkin" Dream Mirror; affordability in "hours of work and days of goal delay". — [fundbun](https://github.com/odripads/fundbun)
- **Real-world grounding:** Sathi uses real published bank rate sheets and fee schedules ("Anything not published is labelled as an assumption") and quotes student interviews. — [finbuddy](https://github.com/Tasrif-Ahmed-Mohsin/finbuddy)
- **Multilingual and colloquial input:** Bangla mandates (Sathi); Cantonese, Hokkien and Manglish (DialectGuard); a scam arriving in Mandarin (Guardian). — sources in §2
- **Story mode:** Sathi's 10-step "Sense → Plan → Act → Prove" walkthrough that the demo video follows. — [finbuddy](https://github.com/Tasrif-Ahmed-Mohsin/finbuddy)
- **Rubric-mapped README:** several entrants map each rubric line to features and evidence IDs ([SamJU25](https://github.com/SamJU25/F-SME-Finance-Copilot); [tanhongsheng](https://github.com/tanhongsheng050204-code/2026-SHENZHEN-FINTECHATHON-INTERNATIONAL-TRACK)).
- **Past FinTechathon pattern:** privacy-preserving computation (FATE federated learning) features in multiple first prizes. — §2 sources

### Inferences
- PaySense already has much of this layer (three tiers, confirm-only writes, an injection and security suite, `scripts/demo_run.py` evidence, a guided "try this" strip). Matching rivals means **surfacing it on screen** (judge mode, a glass-box trace, an attack scoreboard mapped to the four named classes) more than building new security.
- Mechanics that are **under-used in the visible Topic A field** and suit PaySense's assets:
  1. A **measured counterfactual or outcome evaluation**: replaying synthetic student personas through months of BNPL decisions with and without PaySense, and reporting shortfalls avoided, late-fee exposure avoided and the false-alarm rate against benchmarks. This would answer "measurable value" with numbers from the engines.
  2. An **ML-grade evaluation panel** (calibration, benchmarks, SHAP reasons) that rivals using rule-based scores cannot show.
  3. A **privacy-preserving or federated nod**, which is WeBank's signature technology.
  4. A **"fooled versus harmed" split** for the LLM: the model can be fooled into proposing, but nothing executes without the user.
- The single biggest differentiator available to PaySense is probably **measured, benchmarked decision quality on the BNPL affordability question**. Every rival claims safety; none visible claims a validated predictive engine.

### Gaps
- No evidence on which of these mechanics actually won prizes in 2026; finals have not happened.
- No user-study evidence from rivals beyond Sathi's quoted interviews.

---

## 5. Common pitfalls judges and rival teams call out

### Takeaway
The documented pitfalls are:
- LLM wrappers with no deterministic core;
- "LLM guarding an LLM" security;
- made-up or unbacked numbers;
- too many shallow features;
- features copied from existing apps;
- safety hidden in slides instead of on screen;
- a single visible security failure, which triggers "substantial deductions".

### Cited Findings
- "Serious security failures trigger substantial deductions" (official rules page, per two teams). — [leash SUBMISSION.md](https://github.com/Brieuclerouxtardif/leash/blob/HEAD/docs/SUBMISSION.md); [guardian](https://github.com/ahammadshawki8/guardian/blob/HEAD/Guardian.md)
- A rival's rejected-idea analysis lists the failure modes:
  - "Barely touches the security criterion (it mostly advises; there's no permission design)";
  - "Every feature exists in Float, QuickBooks…";
  - "'Peer Mirror' needs benchmark data we don't have, so the numbers would be made up";
  - "The headline profit numbers come from synthetic data, which makes it a GPT wrapper on top of a dashboard";
  - "Ten features in 3.5 days means ten shallow ones";
  - "LLM 'security/policy agents' guarding an LLM is the exact pattern Freysa broke";
  - "The multi-agent debate is theatre".
  — [guardian Guardian.md §18.2](https://github.com/ahammadshawki8/guardian/blob/HEAD/Guardian.md)
- Expected hard judge questions: "Why AI if the contract does the safety?", "Isn't this just [existing product]?", "Your attack numbers are self-reported." The prepared answer to the last is reproducibility with one command plus public records. — [guardian §16, §18.3](https://github.com/ahammadshawki8/guardian/blob/HEAD/Guardian.md)
- "Make the safety decisions visible on-screen. Do not bury them in architecture slides." — [Monara judge research](https://github.com/ZoeMohamed/Monara/blob/HEAD/deck/research/sea-market-competition-compliance.md)
- A thin GPT integration no longer impresses ("judges have seen a hundred GPT wrappers"). The search tool flagged this as anecdote, not data. — [HackerEarth](https://www.hackerearth.com/blog/hackathon-ideas) (via search summary)
- Honest-limit disclosure is common among the stronger entrants: Lifeline's open-items list, FundBun's known-limitations section, Sathi's labelling of assumptions. — [lifeline](https://github.com/sanyuktaphanse/lifeline); [fundbun](https://github.com/odripads/fundbun); [finbuddy](https://github.com/Tasrif-Ahmed-Mohsin/finbuddy)

### Inferences
- For PaySense, the riskiest pitfalls are:
  1. Live LLM flakiness during the demo. The Gemini free-tier limits noted in `questions.md` row 17 could produce a visible failure. Guided-mode fallback should be shown deliberately as the rubric's "fallback".
  2. Synthetic-data numbers presented without benchmarks. PaySense's constraint 5 already guards this; keep the benchmarks on every results slide.
  3. Feature sprawl across eight assistant tasks. Lead with one end-to-end BNPL affordability task.
- A new "edge feature" should **strengthen an existing criterion with measurable evidence**, not add surface area. A feature that cannot be evaluated by a script risks the "made-up numbers" critique.

### Gaps
- No first-hand FinTechathon judge feedback on rejected entries.
- No data on how deductions are applied in practice (for example, per failed attack or per category).
