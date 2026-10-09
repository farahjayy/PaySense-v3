import { describe, expect, it } from "vitest";

import type { Forecast } from "@/lib/api/queries";
import { chartSummary, marginPoints, marginTable, notices } from "@/lib/forecast";

const SIM = {
  months: ["2026-10", "2026-11", "2026-12"],
  monthly_margin_p10_sen: [-5000, -9000, -12000],
  monthly_margin_p50_sen: [20000, 15000, 10000],
  monthly_margin_p90_sen: [40000, 35000, 30000],
  cumulative_margin_p10_sen: [-5000, -20000, -40000],
  cumulative_margin_p50_sen: [20000, 35000, 45000],
  cumulative_margin_p90_sen: [40000, 80000, 120000],
  p_shortfall: 0.2,
  worst_month: "2026-11",
  weeks: 13,
  horizon_capped: false,
  bootstrap: "paths",
} satisfies NonNullable<Forecast["simulation"]>;

function forecast(patch: Partial<Forecast> = {}): Forecast {
  return {
    status: "ok",
    as_of: "2026-10-09",
    model: "lstm",
    months_of_history: 6,
    data_through: "2026-10-08",
    stale_days: 1,
    is_stale: false,
    unmatched_items: [],
    suspect_months: [],
    lock_reason: null,
    simulation: SIM,
    band: "Caution",
    health_score: 80,
    ...patch,
  };
}

describe("margin chart data", () => {
  it("shades from the lower edge up by the range, with the middle line unchanged", () => {
    const points = marginPoints(SIM);
    expect(points[1]).toMatchObject({ low: -20000, spread: 100000, middle: 35000, high: 80000 });
    expect(points.map((p) => p.low + p.spread)).toEqual(SIM.cumulative_margin_p90_sen);
  });

  it("gives a table with the same numbers and marks the worst month", () => {
    const rows = marginTable(SIM);
    expect(rows).toHaveLength(3);
    expect(rows[1]).toMatchObject({
      cumulativeLow: "-RM 200.00",
      cumulativeMiddle: "RM 350.00",
      cumulativeHigh: "RM 800.00",
      monthly: "RM 150.00",
      isWorst: true,
    });
    expect(rows.filter((r) => r.isWorst)).toHaveLength(1);
  });

  it("summarises the chart in a sentence that names the end value and the tightest month", () => {
    expect(chartSummary(SIM)).toBe(
      "By December 2026 your running margin is most likely about RM 450.00. The tightest point is November 2026.",
    );
  });
});

describe("notices", () => {
  it("says nothing when the forecast is clean", () => {
    expect(notices(forecast())).toEqual([]);
  });

  it("explains a stale ledger with the date and the age", () => {
    const [stale] = notices(
      forecast({ is_stale: true, stale_days: 20, data_through: "2026-09-19" }),
    );
    expect(stale.tone).toBe("warning");
    expect(stale.body).toMatch(/19 September 2026/);
    expect(stale.body).toMatch(/20 days ago/);
  });

  it("passes on each incomplete month with the server's own explanation", () => {
    const out = notices(
      forecast({
        suspect_months: [
          { month: "2026-08", reason: "no_income", detail: "No income was logged." },
        ],
      }),
    );
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({
      title: "August 2026 looks incomplete",
      body: "No income was logged.",
    });
  });

  it("lists recurring items that matched nothing", () => {
    const out = notices(forecast({ unmatched_items: ["Rent", "Netflix"] }));
    expect(out[0].body).toMatch(/Rent, Netflix/);
  });

  it("flags a rough range and a capped horizon, but not the normal case", () => {
    expect(notices(forecast({ simulation: { ...SIM, bootstrap: "fallback" } }))[0].id).toBe(
      "bootstrap",
    );
    expect(
      notices(forecast({ simulation: { ...SIM, bootstrap: "paths", horizon_capped: true } }))[0].id,
    ).toBe("capped");
  });

  it("works for a locked forecast, which has no simulation", () => {
    expect(notices(forecast({ status: "locked", simulation: null, band: null }))).toEqual([]);
  });
});
