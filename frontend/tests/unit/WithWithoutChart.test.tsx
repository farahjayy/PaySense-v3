import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WithWithoutChart } from "@/components/risk/WithWithoutChart";
import type { RiskCheck } from "@/lib/api/queries";

type Curve = NonNullable<RiskCheck["with_plan_curve"]>;

const WITH: Curve = {
  months: ["2026-01", "2026-02"],
  cumulative_p10_sen: [-30000, -60000],
  cumulative_p50_sen: [-10000, -25000],
  cumulative_p90_sen: [5000, 10000],
};
const WITHOUT: Curve = { ...WITH, cumulative_p50_sen: [10000, 15000] };

describe("WithWithoutChart", () => {
  it("says in words what the purchase does to the margin and repeats every number", () => {
    render(<WithWithoutChart withPlan={WITH} without={WITHOUT} />);
    expect(
      screen.getByRole("img", {
        name: /by february 2026 .* about -RM 250\.00 with this purchase, against RM 150\.00 without it/i,
      }),
    ).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByText("-RM 600.00")).toBeInTheDocument();
  });

  it("says so when there are no months", () => {
    const empty: Curve = {
      months: [],
      cumulative_p10_sen: [],
      cumulative_p50_sen: [],
      cumulative_p90_sen: [],
    };
    render(<WithWithoutChart withPlan={empty} without={empty} />);
    expect(screen.getByRole("img", { name: "No months to show." })).toBeInTheDocument();
  });
});
