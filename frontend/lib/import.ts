/**
 * Review state for a CSV import: what the preview returned, plus the person's decisions. The
 * server keeps nothing between preview and confirm (D-29), so everything confirmed is rebuilt from
 * here, and the server re-validates it.
 */
import type { ConfirmRow, ImportPreview } from "@/lib/api/queries";

export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;

const FILE_EXTENSIONS = [".csv", ".tsv", ".txt", ".xlsx", ".xlsm"] as const;
/** The file picker's `accept` value: CSV and text exports, and Excel workbooks. */
export const ACCEPTED_FILES = [
  ...FILE_EXTENSIONS,
  "text/csv",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
].join(",");

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

/** The app's categories, then any others a file carried (each once, alphabetical), so a category the
 * person wrote in their own spreadsheet stays on offer. */
export function categoryOptions(extra: Iterable<string> = []): string[] {
  const known = new Set<string>(CATEGORIES);
  const own = new Set<string>();
  for (const category of extra) if (!known.has(category)) own.add(category);
  return [...CATEGORIES, ...[...own].sort((a, b) => a.localeCompare(b))];
}

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
  const name = file.name.toLowerCase();
  if (name.endsWith(".xls")) {
    return "Old Excel files (.xls) can't be read. In Excel choose File > Save As and pick Excel Workbook (.xlsx) or CSV.";
  }
  if (!FILE_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return "Please choose a CSV or Excel (.xlsx) file.";
  }
  if (file.size === 0) return "That file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) {
    return "That file is over 5 MB. Export a shorter date range and try again.";
  }
  return null;
}
