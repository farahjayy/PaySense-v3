import { describe, expect, it } from "vitest";

import {
  barPercent,
  NOT_BUDGETABLE,
  paceLine,
  remainingLine,
  spentOfLimit,
  STATE_COPY,
} from "@/lib/budgets";

describe("budget helpers", () => {
  it("draws the bar from the share spent, capped at full", () => {
    expect(barPercent(0.8)).toBe(80);
    expect(barPercent(1.6)).toBe(100);
    expect(barPercent(0)).toBe(0);
    expect(barPercent(Number.NaN)).toBe(0);
  });

  it("writes spent, remaining and over in ringgit", () => {
    expect(spentOfLimit(8000, 10000)).toBe("RM 80.00 of RM 100.00");
    expect(remainingLine(2000)).toBe("RM 20.00 left");
    expect(remainingLine(-1250)).toBe("RM 12.50 over");
  });

  it("says the pace only when there is a projection", () => {
    expect(paceLine(null, null)).toBeNull();
    expect(paceLine(12000, "over")).toBe(
      "At this pace about RM 120.00 by the end of the month, past the limit.",
    );
    expect(paceLine(5000, "ok")).toBe("At this pace about RM 50.00 by the end of the month.");
  });

  it("gives every state its own glyph, not only a colour", () => {
    const glyphs = Object.values(STATE_COPY).map((s) => s.glyph);
    expect(new Set(glyphs).size).toBe(3);
  });

  it("knows the categories that cannot have a budget", () => {
    expect(NOT_BUDGETABLE.has("Refund")).toBe(true);
    expect(NOT_BUDGETABLE.has("Food")).toBe(false);
  });
});
