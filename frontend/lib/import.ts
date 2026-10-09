/**
 * Review state for a CSV import: what the preview returned, plus the person's decisions. The
 * server keeps nothing between preview and confirm (D-29), so everything confirmed is rebuilt from
 * here, and the server re-validates it.
 */
import type { ConfirmRow, ImportPreview } from "@/lib/api/queries";

export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;

/** The categories the importer guesses from, plus the catch-all. Refund and Transfer matter: the
 * forecast nets refunds against spending and ignores transfers between a person's own accounts. */
export const CATEGORIES = [
  "Food",
  "Transport",
  "Rent",
  "Salary",
  "Allowance",
  "Shopping",
  "Bills",
  "Entertainment",
  "Education",
  "Refund",
  "Transfer",
  "Other",
] as const;

export type RowType = ConfirmRow["type"];

export type ReviewRow = {
  row: number;
  date: string;
  amountSen: number;
  type: RowType;
  category: string;
  description: string;
  issues: readonly string[];
  duplicate: boolean;
  include: boolean;
};

/** Duplicates start unticked: importing the same statement twice must not double the ledger. */
export function toReviewRows(preview: ImportPreview): ReviewRow[] {
  return preview.rows.map((r) => ({
    row: r.row,
    date: r.date,
    amountSen: r.amount_sen,
    type: r.type,
    category: r.category_guess,
    description: r.description ?? "",
    issues: r.issues,
    duplicate: r.duplicate,
    include: !r.duplicate,
  }));
}

export function patchRow(
  rows: readonly ReviewRow[],
  row: number,
  patch: Partial<Pick<ReviewRow, "category" | "type" | "include">>,
): ReviewRow[] {
  return rows.map((r) => (r.row === row ? { ...r, ...patch } : r));
}

export function setAllIncluded(rows: readonly ReviewRow[], include: boolean): ReviewRow[] {
  return rows.map((r) => ({ ...r, include }));
}

export function toConfirmRows(rows: readonly ReviewRow[]): ConfirmRow[] {
  return rows
    .filter((r) => r.include)
    .map((r) => ({
      date: r.date,
      amount_sen: r.amountSen,
      type: r.type,
      category: r.category,
      description: r.description === "" ? null : r.description,
    }));
}

export type ReviewTotals = {
  included: number;
  duplicates: number;
  needAttention: number;
  incomeSen: number;
  spendSen: number;
};

export function totals(rows: readonly ReviewRow[]): ReviewTotals {
  let incomeSen = 0;
  let spendSen = 0;
  let included = 0;
  for (const r of rows) {
    if (!r.include) continue;
    included += 1;
    if (r.type === "income") incomeSen += r.amountSen;
    else if (r.type === "expense") spendSen += r.amountSen;
  }
  return {
    included,
    duplicates: rows.filter((r) => r.duplicate).length,
    needAttention: rows.filter((r) => r.issues.length > 0).length,
    incomeSen,
    spendSen,
  };
}

/** A problem with the file itself, found before anything is uploaded. */
export function fileProblem(file: { name: string; size: number }): string | null {
  if (!file.name.toLowerCase().endsWith(".csv")) return "Please choose a .csv file.";
  if (file.size === 0) return "That file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) {
    return "That file is over 5 MB. Export a shorter date range and try again.";
  }
  return null;
}
