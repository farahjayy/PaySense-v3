import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecentMonths } from "@/components/forecast/RecentMonths";
import type { MonthSummary } from "@/lib/api/queries";

function month(key: string, income: number, spend: number): MonthSummary["months"][number] {
  return {
    month: key,
    income_sen: income,
    spend_sen: spend,
    refund_sen: 0,
    savings_sen: 0,
    net_sen: income - spend,
  };
}

const SUMMARY: MonthSummary = {
  months: [
    month("2026-02", 100000, 138547),
    month("2026-03", 100000, 73353),
    month("2026-04", 100000, 77029),
    month("2026-05", 300000, 205680),
    month("2026-06", 0, 71866),
    month("2026-07", 0, 83467),
    month("2026-01", 100000, 90000),
  ],
  history: null,
};

describe("RecentMonths", () => {
  it("shows the latest six months, newest first, with compact month names", () => {
    render(<RecentMonths summary={SUMMARY} />);

    const names = within(screen.getByRole("table"))
      .getAllByRole("rowheader")
      .map((header) => header.textContent);

    expect(names).toEqual(["Jul 2026", "Jun 2026", "May 2026", "Apr 2026", "Mar 2026", "Feb 2026"]);
  });

  it("gives all four figures per month and marks a month that ended short", () => {
    render(<RecentMonths summary={SUMMARY} />);

    const july = screen.getByRole("row", { name: /jul 2026/i });
    expect(within(july).getByText("RM 0.00")).toBeInTheDocument();
    expect(within(july).getByText("RM 834.67")).toBeInTheDocument();
    expect(within(july).getByText("-RM 834.67")).toHaveClass("text-danger");
    const may = screen.getByRole("row", { name: /may 2026/i });
    expect(within(may).getByText("RM 943.20")).not.toHaveClass("text-danger");
  });

  it("fits its card: nothing in it scrolls sideways, so no figure is cropped", () => {
    const { container } = render(<RecentMonths summary={SUMMARY} />);

    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    expect(container.querySelector(".overflow-x-auto")).toBeNull();
    expect(screen.getByRole("table")).not.toHaveClass("min-w-[26rem]");
  });

  it("shows nothing for a person with no months yet", () => {
    const { container } = render(<RecentMonths summary={{ months: [], history: null }} />);

    expect(container).toBeEmptyDOMElement();
  });
});
