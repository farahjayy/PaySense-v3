import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// The backend has the same text in tests/domain/test_upload.py and proves the importer reads it
// cleanly. This is the other half: what is served is exactly that.
const TEMPLATE = readFileSync(join(process.cwd(), "public", "paysense-import-template.csv"), "utf8");

describe("the import template", () => {
  it("starts with the columns the importer reads: type, date, item, amount, category", () => {
    expect(TEMPLATE.split(/\r?\n/)[0]).toBe("type,date,item,amount,category");
  });

  it("is the exact text the backend test imports cleanly", () => {
    expect(TEMPLATE.replace(/\r\n/g, "\n")).toBe(
      [
        "type,date,item,amount,category",
        "expense,2026-06-01,Nasi lemak,6.50,Food",
        "expense,2026-06-02,Bus to campus,3.00,Transport",
        "income,2026-06-05,PESP Allowance,1000.00,Allowance",
        "",
      ].join("\n"),
    );
  });

  it("holds only invented examples", () => {
    for (const line of TEMPLATE.split(/\r?\n/).slice(1).filter(Boolean)) {
      expect(line.split(",")).toHaveLength(5);
    }
  });
});
