import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarginFan } from "@/components/forecast/MarginFan";
import type { Forecast } from "@/lib/api/queries";

const SIM = {
  months: ["2026-10", "2026-11"],
  monthly_margin_p10_sen: [-5000, -9000],
  monthly_margin_p50_sen: [20000, 15000],
  monthly_margin_p90_sen: [40000, 35000],
  cumulative_margin_p10_sen: [-5000, -20000],
  cumulative_margin_p50_sen: [20000, 35000],
  cumulative_margin_p90_sen: [40000, 80000],
  p_shortfall: 0.2,
  worst_month: "2026-11",
  weeks: 8,
  horizon_capped: false,
  bootstrap: "paths",
} satisfies NonNullable<Forecast["simulation"]>;

describe("MarginFan", () => {
  it("describes the chart in words and repeats every number in a table", () => {
    render(<MarginFan simulation={SIM} />);

    expect(
      screen.getByRole("img", {
        name: /most likely about RM 350\.00.*tightest point is November 2026/i,
      }),
    ).toBeInTheDocument();

    const table = screen.getByRole("table", { name: /forecast running margin by month/i });
    const november = within(table).getByRole("row", { name: /november 2026/i });
    expect(within(november).getByText("-RM 200.00")).toBeInTheDocument();
    expect(within(november).getByText("RM 350.00")).toBeInTheDocument();
    expect(within(november).getByText("RM 800.00")).toBeInTheDocument();
    expect(within(november).getByText("tightest")).toBeInTheDocument();
  });

  it("names the columns in plain words: this month alone, then the total so far in three cases", () => {
    render(<MarginFan simulation={SIM} />);

    const table = screen.getByRole("table", { name: /forecast running margin by month/i });
    const headers = within(table)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(headers).toEqual([
      "Month",
      "This month alone",
      "Total so far, bad case",
      "Total so far, typical",
      "Total so far, good case",
    ]);
  });

  it("says why the columns do not add up, instead of leaving the reader to think it is a mistake", () => {
    render(<MarginFan simulation={SIM} />);

    expect(screen.getByText(/do not add up line by line/i)).toBeInTheDocument();
    expect(screen.getByText(/typical total is not the sum of the typical months/i)).toBeInTheDocument();
  });

  it("explains the chart in three short statements a student can check against it", () => {
    render(<MarginFan simulation={SIM} />);

    const caption = screen.getByText(/the line is the most likely total/i).closest("figcaption");
    expect(caption).toHaveTextContent("8 out of 10");
    expect(caption).toHaveTextContent(/below the dashed line.*short/i);
  });
});
