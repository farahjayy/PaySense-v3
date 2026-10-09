import { describe, expect, it } from "vitest";

import { BAND_COPY, formatDate, formatMonth, formatPercent, plural } from "@/lib/format";

describe("formatDate", () => {
  it("reads the day from the text so no time zone can move it", () => {
    expect(formatDate("2025-05-12")).toBe("12 May 2025");
    expect(formatDate("2025-12-01")).toBe("1 December 2025");
  });

  it("hands back what it cannot read instead of inventing a date", () => {
    expect(formatDate("12/05/2025")).toBe("12/05/2025");
    expect(formatDate("2025-13-01")).toBe("2025-13-01");
  });
});

describe("formatMonth", () => {
  it("names the month, in full or short", () => {
    expect(formatMonth("2025-05")).toBe("May 2025");
    expect(formatMonth("2026-01", true)).toBe("Jan 26");
  });

  it("hands back what it cannot read", () => {
    expect(formatMonth("May")).toBe("May");
    expect(formatMonth("2025-00")).toBe("2025-00");
  });
});

describe("formatPercent", () => {
  it("rounds to a whole percent", () => {
    expect(formatPercent(0.234)).toBe("23%");
    expect(formatPercent(1)).toBe("100%");
    expect(formatPercent(0)).toBe("0%");
  });

  it("never shows a possible shortfall as zero", () => {
    expect(formatPercent(0.002)).toBe("under 1%");
  });
});

describe("plural", () => {
  it("counts and pluralises", () => {
    expect(plural(1, "month")).toBe("1 month");
    expect(plural(3, "month")).toBe("3 months");
    expect(plural(2, "category", "categories")).toBe("2 categories");
  });
});

describe("BAND_COPY", () => {
  it("carries text and an icon for every band, so colour is never the only signal", () => {
    for (const band of ["Safe", "Caution", "At Risk"] as const) {
      expect(BAND_COPY[band].icon.length).toBeGreaterThan(0);
      expect(BAND_COPY[band].line.length).toBeGreaterThan(10);
    }
  });
});
