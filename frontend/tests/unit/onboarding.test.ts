import { describe, expect, it } from "vitest";

import { gettingStartedSteps, type StepInput } from "@/lib/onboarding";

const NOTHING_YET: StepInput = {
  monthsOfHistory: 0,
  recurringCount: 0,
  limitsRecorded: 0,
  forecastReady: false,
  riskChecked: false,
};

function done(input: StepInput): Record<string, boolean> {
  return Object.fromEntries(gettingStartedSteps(input).map((s) => [s.id, s.done]));
}

describe("gettingStartedSteps", () => {
  it("lists the five steps in the order a student should do them", () => {
    expect(gettingStartedSteps(NOTHING_YET).map((s) => s.id)).toEqual([
      "history",
      "recurring",
      "limits",
      "forecast",
      "risk",
    ]);
  });

  it("starts with nothing done", () => {
    expect(Object.values(done(NOTHING_YET))).toEqual([false, false, false, false, false]);
  });

  it("counts history done from four months, and says how far along it is before that", () => {
    const short = gettingStartedSteps({ ...NOTHING_YET, monthsOfHistory: 2 })[0];
    const enough = gettingStartedSteps({ ...NOTHING_YET, monthsOfHistory: 4 })[0];

    expect(short.done).toBe(false);
    expect(short.detail).toBe("2 of 4 months so far");
    expect(enough.done).toBe(true);
    expect(enough.detail).toBeUndefined();
  });

  it("does not claim more than four months of four", () => {
    expect(gettingStartedSteps({ ...NOTHING_YET, monthsOfHistory: 9 })[0].detail).toBeUndefined();
  });

  it("marks recurring, limits, forecast and risk done from the matching facts", () => {
    expect(done({ ...NOTHING_YET, recurringCount: 1 }).recurring).toBe(true);
    expect(done({ ...NOTHING_YET, limitsRecorded: 1 }).limits).toBe(true);
    expect(done({ ...NOTHING_YET, forecastReady: true }).forecast).toBe(true);
    expect(done({ ...NOTHING_YET, riskChecked: true }).risk).toBe(true);
  });

  it("sends each step that needs doing to the page where it is done, but not the forecast", () => {
    const hrefs = Object.fromEntries(gettingStartedSteps(NOTHING_YET).map((s) => [s.id, s.href]));

    expect(hrefs).toEqual({
      history: "/import",
      recurring: "/recurring",
      limits: "/plans",
      forecast: undefined,
      risk: "/risk",
    });
  });

  it("gives every step a sentence on why it matters", () => {
    for (const step of gettingStartedSteps(NOTHING_YET)) {
      expect(step.why.length).toBeGreaterThan(30);
    }
  });
});
