import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { BnplBox } from "@/components/transactions/BnplBox";
import { CategorySpending } from "@/components/transactions/CategorySpending";
import { MonthStepper } from "@/components/transactions/MonthStepper";
import { TypeButtons } from "@/components/transactions/TypeButtons";
import type { CategorySummary, Plan } from "@/lib/api/queries";

const SUMMARY: CategorySummary = {
  month: "2026-06",
  income_sen: 100000,
  spend_sen: 9000,
  gross_spend_sen: 10000,
  refund_sen: 1000,
  savings_sen: 2500,
  categories: [
    { category: "Food", spend_sen: 6000, count: 4, share: 0.6 },
    { category: "Transport", spend_sen: 3000, count: 1, share: 0.3 },
    { category: "BNPL", spend_sen: 1000, count: 1, share: 0.1 },
  ],
};

describe("TypeButtons", () => {
  it("shows every type as a button and marks the chosen one", () => {
    render(<TypeButtons value="income" onChange={() => {}} />);

    const group = screen.getByRole("group", { name: "Type" });
    expect(within(group).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "All",
      "Income",
      "Spending",
      "Savings",
    ]);
    expect(within(group).getByRole("button", { name: "Income" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(group).getByRole("button", { name: "All" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("marks All when nothing is chosen, and reports each choice (All as nothing)", async () => {
    const onChange = vi.fn();
    render(<TypeButtons value={undefined} onChange={onChange} />);

    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Spending" }));
    expect(onChange).toHaveBeenLastCalledWith("expense");
    await userEvent.click(screen.getByRole("button", { name: "All" }));
    expect(onChange).toHaveBeenLastCalledWith(undefined);
  });
});

describe("MonthStepper", () => {
  it("names the month and steps one month either way", async () => {
    const onChange = vi.fn();
    render(<MonthStepper month="2026-06" min="2026-01" max="2026-10" onChange={onChange} />);

    expect(screen.getByText("June 2026")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /previous month/i }));
    expect(onChange).toHaveBeenLastCalledWith("2026-05");
    await userEvent.click(screen.getByRole("button", { name: /next month/i }));
    expect(onChange).toHaveBeenLastCalledWith("2026-07");
  });

  it("cannot go before the first month or after the last", () => {
    const { rerender } = render(
      <MonthStepper month="2026-01" min="2026-01" max="2026-10" onChange={() => {}} />,
    );
    expect(screen.getByRole("button", { name: /previous month/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /next month/i })).toBeEnabled();

    rerender(<MonthStepper month="2026-10" min="2026-01" max="2026-10" onChange={() => {}} />);
    expect(screen.getByRole("button", { name: /next month/i })).toBeDisabled();
  });
});

describe("CategorySpending", () => {
  function panel(over: Partial<Parameters<typeof CategorySpending>[0]> = {}) {
    return (
      <CategorySpending
        month="2026-06"
        summary={SUMMARY}
        isPending={false}
        error={null}
        selected={undefined}
        onSelect={() => {}}
        {...over}
      />
    );
  }

  it("lists each category with its amount and share, biggest first", () => {
    render(panel());

    const rows = screen.getAllByRole("button");
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringContaining("Food"),
      expect.stringContaining("Transport"),
      expect.stringContaining("BNPL"),
    ]);
    expect(within(rows[0]).getByText("RM 60.00")).toBeInTheDocument();
    expect(within(rows[0]).getByText("60%")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Spending by category" })).toBeInTheDocument();
    expect(screen.getByText("June 2026")).toBeInTheDocument();
  });

  it("totals the month: income, what was spent after refunds, and what was saved", () => {
    render(panel());

    const totals = screen.getByRole("group", { name: /totals for june 2026/i });
    expect(within(totals).getByText("Income")).toBeInTheDocument();
    expect(within(totals).getByText("RM 1,000.00")).toBeInTheDocument();
    expect(within(totals).getByText("Spent")).toBeInTheDocument();
    expect(within(totals).getByText("RM 90.00")).toBeInTheDocument();
    expect(within(totals).getByText("Saved")).toBeInTheDocument();
    expect(within(totals).getByText("RM 25.00")).toBeInTheDocument();
    expect(within(totals).getByText("Refunded")).toBeInTheDocument();
    // the rows above add up to the figure before refunds, so the panel reconciles
    expect(within(totals).getByText("Before refunds")).toBeInTheDocument();
    expect(within(totals).getByText("RM 100.00")).toBeInTheDocument();
  });

  it("leaves out Saved and Refunded when there were none", () => {
    render(panel({ summary: { ...SUMMARY, savings_sen: 0, refund_sen: 0, spend_sen: 10000 } }));

    expect(screen.queryByText("Saved")).not.toBeInTheDocument();
    expect(screen.queryByText("Refunded")).not.toBeInTheDocument();
    expect(screen.queryByText("Before refunds")).not.toBeInTheDocument();
  });

  it("picks a category to filter by, and picking it again lets go", async () => {
    const onSelect = vi.fn();
    const { rerender } = render(panel({ onSelect }));

    await userEvent.click(screen.getByRole("button", { name: /transport/i }));
    expect(onSelect).toHaveBeenLastCalledWith("Transport");

    rerender(panel({ onSelect, selected: "Transport" }));
    const chosen = screen.getByRole("button", { name: /transport/i });
    expect(chosen).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(chosen);
    expect(onSelect).toHaveBeenLastCalledWith(undefined);
  });

  it("says so when nothing was spent that month", () => {
    render(
      panel({
        summary: { ...SUMMARY, categories: [], gross_spend_sen: 0, spend_sen: 0, refund_sen: 0 },
      }),
    );

    expect(screen.getByText(/nothing spent in june 2026/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows a loading state and an error without any made-up figures", () => {
    const { rerender } = render(panel({ summary: undefined, isPending: true }));
    expect(screen.getByRole("status", { name: /loading spending/i })).toBeInTheDocument();

    rerender(panel({ summary: undefined, isPending: false, error: "No connection." }));
    expect(screen.getByRole("alert")).toHaveTextContent("No connection.");
    expect(screen.queryByText(/RM/)).not.toBeInTheDocument();
  });
});

describe("BnplBox", () => {
  const PLAN = {
    id: "p1",
    item_name: "ramen",
    provider_label: "SPayLater",
    paid_count: 1,
    num_installments: 3,
  } as Plan;

  it("names the plan, how far it has got, and where it is managed", () => {
    render(<BnplBox plan={PLAN} />);

    const box = screen.getByRole("link", { name: /managed in plans/i });
    expect(box).toHaveAttribute("href", "/plans");
    expect(within(box).getByText("BNPL plan")).toBeInTheDocument();
    expect(within(box).getByText("SPayLater · ramen")).toBeInTheDocument();
    expect(within(box).getByText("1 of 3 paid")).toBeInTheDocument();
  });

  it("still says what it is before the plans have loaded", () => {
    render(<BnplBox plan={undefined} />);

    const box = screen.getByRole("link", { name: /managed in plans/i });
    expect(within(box).getByText("BNPL plan")).toBeInTheDocument();
    expect(within(box).queryByText(/paid/)).not.toBeInTheDocument();
  });
});
