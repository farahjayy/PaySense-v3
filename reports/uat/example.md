# UAT analysis

> **Invented example data.** These answers were made up to test the script. They are not results and must not be quoted as findings.

## System Usability Scale

Mean SUS **75.4** from 6 testers (95% CI 58.9 to 92.0). A score of about 68 is the usual benchmark for average usability.

| Tester | SUS |
|---|---|
| P01 | 92.5 |
| P02 | 75.0 |
| P03 | 50.0 |
| P04 | 87.5 |
| P05 | 82.5 |
| P06 | 65.0 |

## Explanation clarity (1 = strongly disagree, 5 = strongly agree)

| Item | Mean | n |
|---|---|---|
| C1 | 4.17 | 6 |
| C2 | 3.83 | 6 |
| C3 | 3.83 | 6 |
| C4 | 3.83 | 6 |

## Decisions before and after the risk check

Counts only: with this few testers a significance test would overstate the evidence. Safer / riskier follows the risk ranking of the options in `uat/vignettes.yaml`.

| Vignette | Testers | Same | Safer | Riskier | Confidence before | Confidence after |
|---|---|---|---|---|---|---|
| V1: Headphones on SPayLater | 6 | 4 | 2 | 0 | 3.50 | 3.83 |
| V2: Laptop repair on Atome | 6 | 2 | 3 | 1 | 3.33 | 3.67 |
| V3: Shoes on TikTok PayLater | 6 | 3 | 3 | 0 | 3.67 | 3.67 |

**V1** changes: A to C: 1, A to D: 1

**V2** changes: A to C: 1, A to D: 1, B to C: 1, C to B: 1

**V3** changes: A to B: 1, B to C: 1, B to D: 1
