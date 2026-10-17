import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InsightsScreen } from "@/components/screens/InsightsScreen";

import { ok, RECS, wrapper } from "./topicTestUtils";

const get = vi.fn();
const put = vi.fn();
vi.mock("@/lib/api/client", () => ({
  api: { GET: (...a: unknown[]) => get(...a), PUT: (...a: unknown[]) => put(...a) },
}));

const BILLS = {
  as_of: "2026-10-10",
  window_days: 30,
  collision_window_days: 7,
  recurring: {
    count: 2,
    monthly_total_sen: 45000,
    monthly_income_sen: 90000,
    bills_share: 0.5,
    items: [],
  },
  increases: [
    {
      item_id: "u1",
      name: "Unifi",
      previous_sen: 9900,
      latest_sen: 10900,
      change_sen: 1000,
      change_pct: 0.101,
      previous_date: "2026-08-20",
      latest_date: "2026-09-20",
    },
  ],
  collisions: [
    {
      start: "2026-10-12",
      end: "2026-10-18",
      total_sen: 61600,
      items: [
        {
          kind: "instalment",
          name: "Phone",
          due_date: "2026-10-12",
          amount_sen: 26600,
          overdue: false,
          provider_label: "SPayLater",
          plan_id: "p",
          seq: 1,
          item_id: null,
        },
        {
          kind: "bill",
          name: "Rent bilik",
          due_date: "2026-10-15",
          amount_sen: 35000,
          overdue: false,
          provider_label: null,
          plan_id: null,
          seq: null,
          item_id: "r",
        },
      ],
    },
  ],
  upcoming: [
    {
      kind: "instalment",
      name: "Shoes",
      due_date: "2026-10-01",
      amount_sen: 6000,
      overdue: true,
      provider_label: "Atome",
      plan_id: "q",
      seq: 2,
      item_id: null,
    },
  ],
  upcoming_total_sen: 6000,
};

const SPENDING = {
  month: "2026-09",
  previous_month: "2026-08",
  income_sen: 100000,
  spend_sen: 30000,
  savings_sen: 5000,
  left_over_sen: 70000,
  savings_rate: 0.7,
  set_aside_rate: 0.05,
  headline: "Food spending is up RM 100.00 on last month.",
  headline_rule: "category_up",
  categories: [
    {
      category: "Food",
      spend_sen: 30000,
      previous_sen: 20000,
      change_sen: 10000,
      change_pct: 0.5,
      status: "up",
    },
  ],
  movers: [
    {
      category: "Food",
      spend_sen: 30000,
      previous_sen: 20000,
      change_sen: 10000,
      change_pct: 0.5,
      status: "up",
    },
  ],
  unusual: [
    {
      transaction_id: "t",
      date: "2026-09-04",
      category: "Food",
      description: "Buffet",
      amount_sen: 9000,
      median_sen: 1000,
      threshold_sen: 1222,
    },
  ],
  unusual_note: null,
  mad_k: 3,
};

const MONTHS = { months: [{ month: "2026-08" }, { month: "2026-09" }], history: null };

describe("InsightsScreen", () => {
  beforeEach(() => {
    get.mockReset();
    put.mockReset();
    get.mockImplementation(async (path: string) => {
      if (path === "/api/recommendations") return ok(RECS);
      if (path === "/api/insights/bills") return ok(BILLS);
      if (path === "/api/insights/spending") return ok(SPENDING);
      if (path === "/api/summary/months") return ok(MONTHS);
      throw new Error(`unexpected GET ${path}`);
    });
  });

  it("ranks recommendations and shows where each figure came from", async () => {
    render(<InsightsScreen />, { wrapper });
    const first = await screen.findByText("Transport is over budget");
    const card = first.closest("div.rounded-card") as HTMLElement;
    expect(card).toHaveTextContent("Needs attention");
    expect(card).toHaveTextContent("Spent: RM 60.00 (get_budget_status)");
    expect(within(card).getByRole("link", { name: "Review budgets" })).toHaveAttribute(
      "href",
      "/budgets",
    );
  });

  it("a proposed budget is saved only after the person confirms", async () => {
    put.mockResolvedValue(ok({ category: "Shopping", limit_sen: 20000, updated_at: null }));
    render(<InsightsScreen />, { wrapper });
    await userEvent.click(
      await screen.findByRole("button", { name: "Set a Shopping budget of RM 200.00" }),
    );
    expect(put).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("dialog", { name: /set this budget/i });
    await userEvent.click(within(dialog).getByRole("button", { name: "Confirm" }));
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("/api/budgets", {
        body: { category: "Shopping", limit_sen: 20000 },
      }),
    );
    expect(await within(dialog).findByText("Budget saved")).toBeInTheDocument();
  });

  it("highlights collisions, increases and overdue payments", async () => {
    render(<InsightsScreen />, { wrapper });
    expect(await screen.findByText("2 payments in the same week")).toBeInTheDocument();
    expect(
      screen.getByText(/RM 616.00 is due between 12 October 2026 and 18 October 2026/),
    ).toBeInTheDocument();
    expect(screen.getByText("Unifi went up")).toBeInTheDocument();
    expect(screen.getByText("overdue")).toBeInTheDocument();
    expect(screen.getByText("Share of recurring income").parentElement).toHaveTextContent("50%");
  });

  it("shows the spending headline, movers and unusual transactions", async () => {
    render(<InsightsScreen />, { wrapper });
    expect(
      await screen.findByText("Food spending is up RM 100.00 on last month."),
    ).toBeInTheDocument();
    expect(screen.getByText(/up RM 100.00 \(50%\) on the month before/)).toBeInTheDocument();
    expect(screen.getByText("Buffet")).toBeInTheDocument();
    expect(screen.getByText("Kept").parentElement).toHaveTextContent("70%");
  });
});
