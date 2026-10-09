# Instruments

All are answered on paper or on a form and typed into the CSV templates in `templates/` by the facilitator. Participant ids are `P01`, `P02`, …; names are never written next to answers.

## 1. Decision vignettes (before and after)

The three scenarios and their options are in `vignettes.yaml`. For each vignette:

- **Before** (at the start, before the app is shown): "Which would you do?" Choose one option. "How sure are you, from 1 (not at all) to 5 (completely)?"
- **After** (once the tester has run the BNPL risk check for the same purchase on their persona account): the same two questions again.

Record `pre` and `post` rows in `templates/vignettes.csv`.

## 2. Explanation clarity (after the risk check)

Answer each from 1 (strongly disagree) to 5 (strongly agree):

| Item | Statement |
|---|---|
| C1 | I understood why the risk check gave the result it did. |
| C2 | The reasons it listed matched my own sense of my money. |
| C3 | The suggested change (or the message that nothing helps) was clear. |
| C4 | I could explain the result to a friend in my own words. |

## 3. System Usability Scale (at the end)

Answer each from 1 (strongly disagree) to 5 (strongly agree). Scoring is done by the analysis script.

| Item | Statement |
|---|---|
| S1 | I think that I would like to use this system frequently. |
| S2 | I found the system unnecessarily complex. |
| S3 | I thought the system was easy to use. |
| S4 | I think that I would need the support of a technical person to be able to use this system. |
| S5 | I found the various functions in this system were well integrated. |
| S6 | I thought there was too much inconsistency in this system. |
| S7 | I would imagine that most people would learn to use this system very quickly. |
| S8 | I found the system very cumbersome to use. |
| S9 | I felt very confident using the system. |
| S10 | I needed to learn a lot of things before I could get going with this system. |

The System Usability Scale is by John Brooke (1996).

## 4. Debrief questions (not scored)

1. What, if anything, would you have wanted the risk check to say that it did not?
2. Was there anything it said that you did not believe? Why?
3. Would you use something like this before a real purchase?

Write answers as short notes against the participant id.
