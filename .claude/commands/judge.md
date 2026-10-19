---
description: Run the mock FinTechathon judges panel over PaySense and write a scored verdict
argument-hint: [judge file name, e.g. security-red-teamer | defence-chair] (empty = the whole panel)
allowed-tools: Read, Glob, Grep, Bash, Write, Agent
---

Run the mock judges panel defined in `internal/refdocs/fintechathon-2026/judges/` for: $ARGUMENTS (empty means the whole panel)

1. Read `internal/refdocs/fintechathon-2026/judges/README.md` (the score sheet) and `internal/refdocs/fintechathon-2026/organizer/rules.md` §3 and §11 (the official rubric).
2. Pick the persona files: every `*.md` in that folder except `README.md` and `winning-playbook.md`, or only the one named in the arguments.
3. For each persona, spawn one read-only `general-purpose` agent, all in parallel. Give it the full text of its persona file and these instructions:
   - You are this judge. Judge PaySense v3 as submitted to FinTechathon 2026, Topic A. Read the evidence your persona says it reads first, then anything else in the repo you need. Never edit a file.
   - Score only your sub-criteria from the score sheet, with the anchors. For each score, cite the file (and line, where useful) that earned it or lost it.
   - Treat a number as evidence only if a file in the repo produced it; a claim in a doc with no source counts as "claimed".
   - Output: your sub-scores, three strengths, three weaknesses with the smallest fix for each, and your five hardest questions for the defence.
   - For `defence-chair`: also give a ten-minute timing plan for the deck in `internal/refdocs/fintechathon-2026/submission/final-defence-deck.md`.
4. Combine the results: a table of sub-score / maximum per criterion, the weighted total out of 100, any deduction, and the bonus. Then the five fixes that would gain the most points, ranked. Then the full list of questions, without duplicates.
5. Write the verdict to `internal/refdocs/fintechathon-2026/judges/verdicts/<today's date, YYYY-MM-DD>.md` (create the folder if needed) and show it to the user.

Rules: the judges are imagined personas, so never present a score as the real panel's. Do not change code or other docs from this command; list fixes for the user to approve.
