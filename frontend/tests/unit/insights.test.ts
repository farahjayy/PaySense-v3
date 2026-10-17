import { describe, expect, it } from "vitest";

import { changeLine, formatSource, SEVERITY_COPY } from "@/lib/insights";

const base = { change_pct: null, previous_sen: 0, spend_sen: 0, change_sen: 0 };

describe("insight helpers", () => {
  it("describes each kind of change", () => {
    expect(changeLine({ ...base, status: "new", spend_sen: 9000 })).toBe("new: RM 90.00");
    expect(changeLine({ ...base, status: "gone", previous_sen: 5000 })).toBe(
      "none this month (was RM 50.00)",
    );
    expect(changeLine({ ...base, status: "same" })).toBe("the same as the month before");
    expect(changeLine({ ...base, status: "up", change_sen: 10000, change_pct: 0.5 })).toBe(
      "up RM 100.00 (50%) on the month before",
    );
    expect(changeLine({ ...base, status: "down", change_sen: -2500, change_pct: -0.25 })).toBe(
      "down RM 25.00 (25%) on the month before",
    );
  });

  it("writes a source figure the way its sentence does", () => {
    expect(formatSource({ value: 12000, unit: "sen" })).toBe("RM 120.00");
    expect(formatSource({ value: 0.62, unit: "probability" })).toBe("62%");
    expect(formatSource({ value: "2026-03-12", unit: "date" })).toBe("12 March 2026");
    expect(formatSource({ value: "At Risk", unit: "text" })).toBe("At Risk");
    expect(formatSource({ value: 3, unit: "count" })).toBe("3");
  });

  it("gives every severity a glyph", () => {
    expect(new Set(Object.values(SEVERITY_COPY).map((s) => s.glyph)).size).toBe(3);
  });
});
