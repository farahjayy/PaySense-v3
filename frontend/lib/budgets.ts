/** Display helpers for budgets (WP2/WP3). Pure; every figure arrives from the server in sen. */

import { formatRm } from "@/lib/money";

export type BudgetState = "ok" | "near" | "over";

export const STATE_COPY: Record<
  BudgetState,
  { label: string; glyph: string; bar: string; text: string }
> = {
  ok: { label: "On track", glyph: "✓", bar: "bg-success", text: "text-success" },
  near: { label: "Close to the limit", glyph: "!", bar: "bg-warning", text: "text-warning" },
  over: { label: "Over the limit", glyph: "▲", bar: "bg-danger", text: "text-danger" },
};

/** How wide the bar is drawn: the share spent, capped at a full bar. */
export function barPercent(percent: number): number {
  if (!Number.isFinite(percent) || percent <= 0) return 0;
  return Math.min(percent, 1) * 100;
}

/** "RM 80.00 of RM 100.00" */
export function spentOfLimit(spentSen: number, limitSen: number): string {
  return `${formatRm(spentSen)} of ${formatRm(limitSen)}`;
}

/** What is left, or how far over, in words. */
export function remainingLine(remainingSen: number): string {
  return remainingSen >= 0 ? `${formatRm(remainingSen)} left` : `${formatRm(-remainingSen)} over`;
}

/** The pace sentence for the current month, or null when the server sent no projection. */
export function paceLine(projectedSen: number | null, projectedState: BudgetState | null) {
  if (projectedSen === null || projectedState === null) return null;
  const tail = projectedState === "over" ? ", past the limit" : "";
  return `At this pace about ${formatRm(projectedSen)} by the end of the month${tail}.`;
}

export const INCOME_BASIS_COPY: Record<"recurring" | "average" | "none", string> = {
  recurring: "your confirmed recurring income this month",
  average: "your average income in the months used",
  none: "no income known yet",
};

/** Categories that can never have a budget (the server refuses them too, D-43). */
export const NOT_BUDGETABLE = new Set(["Refund", "Transfer", "BNPL", "Salary", "Allowance"]);
