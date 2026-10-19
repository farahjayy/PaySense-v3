# Demo video — recording script (five minutes or less)

> The shape follows work-packages.md section 6. Every figure on screen comes from the running app; this script names no number, so it stays true when the model or the personas change. Before recording, run `cd backend && uv run python scripts/find_demo_scenario.py` (or `--in-memory`) and `scripts/demo_run.py`, and read `demo-scenario.md` and `evidence/demo-run/SUMMARY.md` for what the model gives today.

## Setup
- Desktop browser at full HD, the assistant panel docked on the right; a phone (or the browser's phone view) for one shot.
- Signed out. The frequent_bnpl demo account (persona history loaded with `load_personas.py`), its passphrase delivered privately, the privacy notice already accepted. A second tab signed in as irregular_income with no savings buffer (the Second-Opinion scene, D-57); a third as budget_conscious. Pick shot 10's account and buffer from the *Adds* and *Safer timing* columns of `demo-scenario.md`: a row whose *Adds* is large and whose timing qualifies (on the current engines that is frequent_bnpl with RM500, so shot 10 is in the first tab).
- The assistant on the configured provider (the status line in the panel says which). If it falls back to guided mode during recording, keep going with the quick actions and say so: that is the designed behaviour.

## Shots

| # | Time | On screen | Say (plain words) |
|---|---|---|---|
| 1 | 0:00–0:20 | Login page: the headline, the three faces, the responsible-use line; open "New to BNPL in Malaysia?" | "Students in Malaysia split phones and laptops into instalments at checkout. PaySense checks whether the next plan fits before they commit. It gives estimates, not advice, and changes nothing until you confirm." |
| 2 | 0:20–0:45 | Sign in with username and passphrase. Dashboard: alert, score ring, band, running-margin chart. | "This is a synthetic student who already uses buy-now-pay-later. The forecast plays the next months forward many times; the band is the range most futures land in, and the alert says when money may run short." |
| 3 | 0:45–1:00 | Press "Ask PaySense": the opening turn lists what needs attention. | "The assistant starts with what needs attention, from the same rules as the dashboard." |
| 4 | 1:00–1:50 | "Try this" step 1 → Send. Risk card; open "What I did" to show the tool and its tier. | "It asks the risk check, it doesn't guess. Every figure it says has to come from that tool, or its words are replaced by the tool's own summary." |
| 5 | 1:50–2:20 | Step 2 → Send. The smallest change, or the honest "none reaches Safe". | "If no small change makes it safe, it says so rather than inventing one." |
| 6 | 2:20–2:50 | Type the full request, "Please add the RM799 SPayLater phone plan over 3 months so I can confirm it." (the short "Go ahead with that." fails on the live model: `questions.md` row 60) → the confirm card with the exact plan → Confirm → open the saved report. | "The model has no write tool. It can only propose; this card is built from the stored proposal, and only my press saves it. Budgets and imports follow the same rule." |
| 7 | 2:50–3:20 | Open the paste box, paste three messy lines (one already in the ledger) → preview with the duplicate flagged → Confirm. | "Every row must be written on one line of what I pasted; anything the model makes up is dropped, and duplicates are left out." |
| 8 | 3:20–3:50 | Security drill page → "Run the drill" → the scoreboard (four attack classes, model fooled, harm done); open one prompt-injection attack. | "Here we attack it on purpose, assuming the model is fooled every time. Each attack runs in a throwaway sandbox, and harm is checked on the data afterwards. The defences hold without the model's help." |
| 9 | 3:50–4:15 | irregular_income tab, Risk check: the RM799 phone. Scroll to "What this purchase adds": the student is already At Risk without it; the month-by-month table of everything owed. | "This is the Second-Opinion Check. A lender looks at one purchase. PaySense runs your next months with and without it, and adds up every instalment you owe across providers. Here the honest answer is that the problem was there before the phone." |
| 10 | 4:15–4:45 | Your data → enter the savings buffer `demo-scenario.md` names for this scene (on the engines served now and the real database: frequent_bnpl with RM1,000, band Caution at 23%, the phone adds about 18 points, and "Spread it over 6 instalments" reaches Safe) → check again. "Adds"; press "Find a better time" → the options tried → "Use this" → the check re-runs. | "With savings entered, the starting point is fine, but this phone still adds about 18 points. The timing search tries the date you entered and the days after your next income, with other instalment counts, and stops at the first that adds little; here it is the same date over 12 instalments, and "Try this" shows that 6 instalments reach Safe. Every number is from the same simulation." |
| 11 | 4:45–5:00 | About the model: what it never looks at; where it is weak. | "Trained on simulated students, not real repayments; its limits are on this page. Thank you." |

## After recording
- Check that no passphrase, key or real person's data is visible in any frame.
- Keep the `evidence/demo-run/` files from the same day with the video.
