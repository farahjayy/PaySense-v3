import { describe, expect, it } from "vitest";

import type { ImportPreview } from "@/lib/api/queries";
import {
  ACCEPTED_FILES,
  CATEGORIES,
  categoryOptions,
  fileProblem,
  MAX_UPLOAD_BYTES,
  patchRow,
  setAllIncluded,
  toConfirmRows,
  toReviewRows,
  totals,
} from "@/lib/import";

const PREVIEW: ImportPreview = {
  rows: [
    {
      row: 2,
      date: "2026-09-01",
      amount_sen: 120000,
      type: "income",
      category_guess: "Allowance",
      description: "PTPTN",
      issues: [],
      duplicate: false,
    },
    {
      row: 3,
      date: "2026-09-02",
      amount_sen: 1850,
      type: "expense",
      category_guess: "Food",
      description: null,
      issues: ["Type guessed from the sign of the amount"],
      duplicate: false,
    },
    {
      row: 4,
      date: "2026-09-03",
      amount_sen: 900,
      type: "expense",
      category_guess: "Transport",
      description: "TNG",
      issues: [],
      duplicate: true,
    },
  ],
  skipped: [{ row: 5, reason: "No amount" }],
  notes: [],
  duplicate_count: 1,
};

describe("import review", () => {
  it("starts with duplicates unticked so a statement cannot be imported twice", () => {
    const rows = toReviewRows(PREVIEW);
    expect(rows.map((r) => r.include)).toEqual([true, true, false]);
  });

  it("confirms only ticked rows, with the edited category and a null for no description", () => {
    const edited = patchRow(toReviewRows(PREVIEW), 3, {
      category: "Shopping",
      type: "expense",
    });
    expect(toConfirmRows(edited)).toEqual([
      {
        date: "2026-09-01",
        amount_sen: 120000,
        type: "income",
        category: "Allowance",
        description: "PTPTN",
      },
      {
        date: "2026-09-02",
        amount_sen: 1850,
        type: "expense",
        category: "Shopping",
        description: null,
      },
    ]);
  });

  it("does not mutate the rows it was given", () => {
    const rows = toReviewRows(PREVIEW);
    const next = patchRow(rows, 2, { include: false });
    expect(rows[0].include).toBe(true);
    expect(next[0].include).toBe(false);
  });

  it("totals what would be added, and counts duplicates and rows with notes", () => {
    const rows = toReviewRows(PREVIEW);
    expect(totals(rows)).toEqual({
      included: 2,
      duplicates: 1,
      needAttention: 1,
      incomeSen: 120000,
      spendSen: 1850,
    });
    expect(totals(setAllIncluded(rows, false)).included).toBe(0);
    expect(totals(setAllIncluded(rows, true)).spendSen).toBe(2750);
  });

  it("catches a wrong, empty or oversized file before uploading", () => {
    expect(fileProblem({ name: "statement.pdf", size: 10 })).toMatch(/CSV or Excel/);
    expect(fileProblem({ name: "statement.csv", size: 0 })).toMatch(/empty/);
    expect(fileProblem({ name: "statement.csv", size: MAX_UPLOAD_BYTES + 1 })).toMatch(/5 MB/);
    expect(fileProblem({ name: "Statement.CSV", size: MAX_UPLOAD_BYTES })).toBeNull();
  });

  it("accepts Excel workbooks and tab or plain-text exports as well as CSV", () => {
    for (const name of ["a.xlsx", "A.XLSM", "a.tsv", "a.txt", "a.csv"]) {
      expect(fileProblem({ name, size: 10 })).toBeNull();
    }
    expect(ACCEPTED_FILES).toContain(".xlsx");
  });

  it("says how to convert an old .xls file instead of just refusing it", () => {
    expect(fileProblem({ name: "budget.xls", size: 10 })).toMatch(/\.xlsx/);
  });
});

describe("category options", () => {
  it("is the app's list, then the file's own categories, each once, in alphabetical order", () => {
    const options = categoryOptions(["Hangout", "Food", "Boyfriend Tax", "Hangout", "Drink / Dessert"]);

    expect(options.slice(0, CATEGORIES.length)).toEqual([...CATEGORIES]);
    expect(options.slice(CATEGORIES.length)).toEqual(["Boyfriend Tax", "Drink / Dessert", "Hangout"]);
  });

  it("is just the app's list when there is nothing extra", () => {
    expect(categoryOptions()).toEqual([...CATEGORIES]);
  });
});
