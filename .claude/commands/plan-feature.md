---
description: Write the plan + execution doc pair required before building
argument-hint: [what you want to build, or a phase id like P1]
allowed-tools: Read, Write, Glob, Grep, Bash
---

Produce the plan/execution pair CLAUDE.md requires before any non-trivial implementation, for: $ARGUMENTS

First read `refdocs/STATUS.md`, `refdocs/paysense-v3-PRD.md` (§3 designs, §6 exit criteria), `refdocs/changelog/DECISIONS.md`, and the code this would touch. If the work ports from v1, read the relevant files in `../PaySense/` (read-only) and name exactly which files and tests are ported. Check whether an existing plan already covers it — if so, say so instead of writing a duplicate.

Write two files with the same filename, matching the structure of the existing docs in those directories:
- `refdocs/plans/YYYY-MM-DD-<slug>.md` — what and why: scope in/out with reasons, approach, a risk table with honest confidence levels, and a definition of done phrased as observable facts.
- `refdocs/execution/YYYY-MM-DD-<slug>.md` — how and in what order: numbered tasks, each naming the files it touches and carrying its own **Verify** step with a real command and expected result. Tests come before implementation.

Where a task depends on an external library's behavior, its first step is "read the actual docs/types/source" — do not encode an API you're recalling from memory. Respect ADRs D-03, D-05, D-07, D-09 and D-14; propose a new ADR rather than diverging. No deadline or schedule language.

Add both files to the index tables in `refdocs/plans/README.md` and `refdocs/execution/README.md`. Do not implement anything. Return both paths and the task order.
