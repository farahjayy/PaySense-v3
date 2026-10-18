# Plan — The Second-Opinion Check (competitive-edge headline)

> Execution: `refdocs/execution/2026-10-18-second-opinion-check.md`. Decision: D-57 in `refdocs/changelog/DECISIONS.md`. Evidence: `refdocs/fintechathon-2026/research/reports/PaySense hackathon edge feature.md`.

## 1. Why this exists
Rivals in Topic A already show permission tiers, confirm-only writes and attack scoreboards; that is now the entry ticket. No rival or product answers the student's real pre-purchase question across every provider: **how much worse does this purchase make my next months, and when would it not?** Malaysia's Consumer Credit Act 2025 makes lenders assess "total commitments" privately; this shows the student the equivalent picture from their own data. The behavioural evidence favours showing the student's own added-up commitments and the change a purchase makes over generic warnings (Bertrand & Morse: adding-up disclosure cut payday borrowing about 11%; the Central Bank of Ireland's warnings changed understanding, not use).

## 2. Scope
**In (stage 1, on the current engines):**
- The risk check returns a `second_opinion` block: the simulated chance of running short **without** the purchase, **with** it, and the **added** chance — all from Engine 1's simulation with one shared seed (the quantity Engine 2's label is built from, D-07) — beside Engine 2's band, score and reasons, which stay as they are.
- A **stacked dues** table: every unpaid instalment by month and provider plus the new plan's, the total, and the confirmed recurring income falling in each month; an exposure line (unpaid across providers before and after) and, where the student recorded provider limits, whether their recorded limits together reach RM1,500 (the level at which BNM's policy document asks banks for a full affordability assessment — mirrored as information, never as compliance).
- A **"find a better time"** scheduler (`POST /api/risk/schedule`): options over start dates (as typed, and after each of the next two confirmed income dates) × instalment counts, each judged by the same simulation; the first option in a fixed order that adds at most 5 points **and** stays below the At Risk edge is suggested. If the student is already At Risk without the purchase, nothing qualifies and the screen says why.
- The assistant: `check_purchase_risk` carries the block; a new Tier 1 tool `find_safer_timing`; the existing `propose_action` (`create_plan`) carries the chosen date and count to the confirm card.
- The risk screen shows the block; the assistant's risk card too.
**Out:** a new reminder write action; the engine changes (bundled v3 build, separate plan); any new model family.

## 3. Approach
Every figure comes from the simulation, the plan rules or the ledger; the frontend formats, never adds. The scheduler reuses `assess`'s shared ledger cache so each option is one with-purchase simulation. When the engines are rebuilt (v3), the same contract carries the new numbers.

## 4. Risks
| Risk | Mitigation |
|---|---|
| A saturated baseline makes "adds 0 points" misleading | The qualifying rule needs the result below the At Risk edge; the card leads with "already likely to run short without it" |
| Scheduler cost (several simulations) | Separate endpoint, rate-limited, at most 3 dates × the provider's counts |
| Reading regulation as compliance | Wording mirrors the lender's duty; the RM1,500 line is labelled as BNM's trigger for banks |

## 5. Definition of done
Tests first for the pure parts and the API; assistant tool and policy tests; frontend tests and a Playwright journey; live check on the persona; docs, ADR, changelog.
