# Plans

> **MANDATORY:** Before implementing any non-trivial feature, a plan document must exist in this folder.
> A plan covers **what** and **why** — goal, scope, constraints, risks, definition of done.
> The **how** and **in what order** belongs in `refdocs/execution/`. When the two merge, both stop being read.

## Naming convention

`YYYY-MM-DD-<slug>.md` — the date the plan was written, then a short kebab-case slug. Phase plans use the phase id in the slug (`p1-ledger-bnpl`, `p3-engine1-evaluation`, …).

**The execution doc uses the identical filename** in `refdocs/execution/`. Same date, same slug — that mirroring is how you find a plan's other half without opening anything. If a plan gets superseded, write a new one and mark the old row Superseded; don't rewrite history in place.

## Required sections in every plan

1. **Why this exists** — the problem, in the user's terms
2. **What's already covered** — what needs no work, so nobody rebuilds it
3. **Scope** — what's in, and what's explicitly out *with reasons*
4. **Approach** — the shape of the solution
5. **Risks & unknowns** — with honest confidence levels. "I read this library's docs" and "I think this library does that" are different rows.
6. **Definition of done** — phrased as observable facts, not intentions

## Index

Add a row when you write a plan. Update the status when it moves — a stale index is how a project ends up with three plans for the same thing.

Status vocabulary: `Draft` · `In progress` · `Done` · `Blocked` · `Superseded` · `On hold`

| File | Description | Status |
|---|---|---|
| [2026-10-08-p0-foundation.md](2026-10-08-p0-foundation.md) | P0 Foundation — toolchain spike, backend/frontend skeletons, username login + user scoping, generated API client, test tooling | In progress — all but live-Supabase checks |
| [2026-10-08-p1-ledger-bnpl.md](2026-10-08-p1-ledger-bnpl.md) | P1 Ledger & BNPL domain — pure-domain ports (schedule, limit split, flows, CSV), repositories, API; no balance (D-27) | In progress |
