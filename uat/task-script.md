# Session script

For the facilitator. About 40 minutes. Say the **bold** lines as written; do not explain the app beyond them. If the tester is stuck for more than a minute, note where, then give the smallest hint you can and note that you did.

## Before the tester arrives

- The tester's practice account exists (`seed_testers.py`) and is on the persona you intend.
- The persona's CSV is on the laptop: `data/personas/<persona>.csv`.
- You have the three blank forms from `templates/` and this script open.
- The app is open on its login page.

## 1. Welcome (3 min)

**"Thanks for helping. This is a test of the app, not of you. Nothing you do is wrong. Please say out loud what you are thinking as you go. I will not be able to help much, because I want to see where it is unclear."**

Hand over the information note (`participant-information.md`). Wait while they read it. Check they have no questions and are happy to go on. Give them a participant code (P01…).

## 2. Scenarios, before (7 min)

Show the three scenarios (`vignettes.yaml`) one at a time. For each: **"Which of these would you do? How sure are you, from 1 to 5?"** Write the answer as a `pre` row in `vignettes.csv`. Do not discuss the answers.

## 3. Tasks (20 min)

Use the persona for the scenario they will check at the end (V1 frequent BNPL, V2 irregular income, V3 budget-conscious). Say each task; do not name the buttons.

| # | Say | Watch for | Note |
|---|---|---|---|
| T1 | **"Log in with the username on this card."** | Finds the login; understands there is no password | |
| T2 | **"This file is a few months of an imaginary student's bank statement. Bring it into the app."** | Finds Import; reads the preview; what they do with duplicates and categories | |
| T3 | **"What does the app say about this student's money over the next few months? Tell me in your own words."** | Reads the score and the band; whether they notice the shaded range and any warnings | |
| T4 | **"Is there anything in the app you would want to tell it that repeats every month?"** | Finds Recurring; understands the suggestions | |
| T5 | **"Now this student is thinking of making the purchase in scenario <V>. Find out whether it is a good idea."** | Finds the risk check; enters the purchase; how they enter the provider and instalments | |
| T6 | **"Read the result out loud and tell me what you make of it."** | Whether the reasons make sense to them; whether they see the suggested change; whether they notice the repayment note | |
| T7 | **"Is there anything you would change about the purchase after seeing this?"** | Whether they use the suggestion | |

Optional T8 (if time): **"Go ahead and add the plan."** Watch that they understand the amount paid at checkout.

After T6, give them the clarity questions (`instruments.md` section 2) and record them in `clarity.csv`.

## 4. Scenarios, after (5 min)

**"Back to the scenario. Which would you do now? How sure are you, from 1 to 5?"** Record `post` rows. Do not say whether the answer changed.

## 5. Usability scale and debrief (5 min)

Give the ten SUS statements (`instruments.md` section 3). Then ask the debrief questions and write short notes.

## What not to say

- Do not say what the result "should" be, or whether a choice is sensible.
- Do not explain a number before they have tried to read it themselves.
- Do not say "the model" or "AI" unless they do first.
- Do not praise or criticise an answer.

## After the session

- Type the three forms into `uat/data/<run>/` (copy the templates; one file each; one row per tester per question).
- Keep the notes with the participant code only.
- Run `cd backend && uv run python -m ml.uat.analyse --data ../uat/data/<run> --out ../reports/uat/<run>.md`.
