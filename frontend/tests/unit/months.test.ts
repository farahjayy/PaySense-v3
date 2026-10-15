import { describe, expect, it } from "vitest";

import { currentMonth, monthBounds, monthOf, shiftMonth, startingMonth } from "@/lib/months";

describe("months", () => {
  it("reads the month out of a date", () => {
    expect(monthOf("2026-06-10")).toBe("2026-06");
  });

  it("steps forwards and backwards across a year end", () => {
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftMonth("2026-06", 0)).toBe("2026-06");
    expect(shiftMonth("2026-03", -14)).toBe("2025-01");
  });

  it("gives the first and last day of a month, leap years included", () => {
    expect(monthBounds("2026-06")).toEqual({ start: "2026-06-01", end: "2026-06-30" });
    expect(monthBounds("2026-02")).toEqual({ start: "2026-02-01", end: "2026-02-28" });
    expect(monthBounds("2028-02")).toEqual({ start: "2028-02-01", end: "2028-02-29" });
    expect(monthBounds("2026-12")).toEqual({ start: "2026-12-01", end: "2026-12-31" });
  });

  it("names this month from the clock it is given", () => {
    expect(currentMonth(new Date(2026, 9, 15))).toBe("2026-10");
    expect(currentMonth(new Date(2026, 0, 1))).toBe("2026-01");
  });

  it("opens on the latest month that has anything in it, else this month", () => {
    const months = [{ month: "2026-05" }, { month: "2026-07" }, { month: "2026-06" }];

    expect(startingMonth(months, "2026-10")).toBe("2026-07");
    expect(startingMonth([], "2026-10")).toBe("2026-10");
    expect(startingMonth(undefined, "2026-10")).toBe("2026-10");
  });
});
