---
description: Close out the session — changelog entry, STATUS update, ADRs, doc reconciliation
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

Close out this session per CLAUDE.md's mandatory rules. Do not skip a step because the session felt small.

1. `git status` and `git diff` — establish what actually changed. Don't rely on memory of the conversation.
2. Add an entry to `internal/refdocs/changelog/CHANGELOG.md` in that file's documented format (newest first). The **Verified** line names a command that was actually run and its actual result; if nothing was run this session, write "nothing verified this session" rather than implying otherwise.
3. Update `internal/refdocs/STATUS.md`: the phase table, and the verification ledger if anything was genuinely verified. Status never rounds up — code that compiles but was never executed is 🔶, not ✅.
4. Any architectural decision made this session → an ADR in `internal/refdocs/changelog/DECISIONS.md`, with an id matching the PRD's §7 decision log (add the one-liner there too). Any `ASSUMED:` that got resolved gets promoted or deleted.
5. If the work diverged from its execution doc, edit that doc to match reality and note it in the changelog's Deviations line.
6. Update the index tables in `internal/refdocs/plans/README.md` and `internal/refdocs/execution/README.md` if a doc was added or changed status. If a new environment variable appeared, add it to `docs/env_setup.md` and the matching `.env.example` now.
7. If model code changed this session, say whether the `ml-auditor` agent was run and what it found.

No deadline or schedule language anywhere. Then show me the changelog entry you wrote, and list anything you couldn't resolve.
