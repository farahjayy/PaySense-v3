# Credits

## Author

PaySense was designed and built by **Nur Farah Binti Ahmad Nazri** as a Final Year Project, BSc (Hons) Computer Science, Universiti Teknologi PETRONAS (supervisor: Dr. Nazleeni Samiha Bt Haron), and extended for the FinTechathon (Topic A). The research questions, the choice of candidate algorithms (from the literature review), the product decisions and every sign-off are the author's.

## AI-assisted development

This repository was built with substantial help from an AI coding assistant (Anthropic's Claude, through Claude Code). We say so plainly because judges and readers should know how the code came to be:

- The assistant worked under written rules in [`CLAUDE.md`](CLAUDE.md) and its preflight checklist: a plan and an execution document before each feature, tests first, every decision recorded in [`refdocs/changelog/DECISIONS.md`](refdocs/changelog/DECISIONS.md) (choices the author has not yet confirmed are marked `ASSUMED`), a changelog entry after every session, and no number in a report that a script did not produce.
- Specialised review agents (definitions in `.claude/agents/`: an ML auditor for leakage and train/serve parity, a test runner, a documentation keeper, a feature planner) and independent security reviews checked the work; their findings and what was done about them are in the changelog.
- Open questions the assistant could not settle are listed for the author in [`refdocs/fintechathon-2026/questions.md`](refdocs/fintechathon-2026/questions.md).
- Commits made with the assistant carry a `Co-Authored-By` line.

The author reviews and merges every change; responsibility for the work is the author's.

## Third-party software and data

Open-source libraries and the two public benchmark datasets (MoneyData, CC BY 4.0; Berka / PKDD'99) are listed with their licences in [`THIRD_PARTY.md`](THIRD_PARTY.md).
