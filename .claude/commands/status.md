---
description: Where is this project actually at?
allowed-tools: Read, Glob, Grep, Bash
---

Tell me where PaySense v3 actually stands.

Read `refdocs/STATUS.md`, the last few `refdocs/changelog/CHANGELOG.md` entries, and any in-progress execution doc. Then check reality: `git log --oneline -10`, `git status`, and the code for the current phase. If tests exist, say whether STATUS's verification ledger is backed by a recent real run.

Report:
- Current phase and what's genuinely done vs claimed done
- Anything STATUS.md says is ✅ that the code or verification ledger doesn't support — flag this loudly, it's the failure mode this file exists to catch
- Open `ASSUMED:` items and blockers
- The single next action

Be blunt about drift. An accurate "STATUS is ahead of reality in two places" is the whole point of running this. No deadline or schedule commentary.
