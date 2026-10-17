import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BudgetsScreen } from "@/components/screens/BudgetsScreen";

import { BUDGET_STATUS, fail, ok, SUGGESTION, wrapper } from "./topicTestUtils";

const get = vi.fn();
const post = vi.fn();
const put = vi.fn();
const del = vi.fn();
vi.mock("@/lib/api/client", () => ({
  api: {
    GET: (...a: unknown[]) => get(...a),
    POST: (...a: unknown[]) => post(...a),
    PUT: (...a: unknown[]) => put(...a),
    DELETE: (...a: unknown[]) => del(...a),
  },
}));

const CATEGORIES = {
  categories: ["Food", "Transport", "Shopping", "Refund", "Salary"].map((name) => ({
    name,
    builtin: true,
    locked: true,
    assignable: true,
    note: null,
    transaction_count: 0,
  })),
};

function routes(status = BUDGET_STATUS) {
  get.mockImplementation(async (path: string) => {
    if (path === "/api/budgets/status") return ok(status);
    if (path === "/api/categories") return ok(CATEGORIES);
    throw new Error(`unexpected GET ${path}`);
  });
}

describe("BudgetsScreen", () => {
  beforeEach(() => {
    for (const m of [get, post, put, del]) m.mockReset();
    routes();
  });

  it("shows each budget's bar, state in words, money and pace", async () => {
    render(<BudgetsScreen />, { wrapper });
    const list = await screen.findByRole("list", { name: /your budgets/i });
    const [food, transport] = within(list).getAllByRole("listitem");
    expect(within(food).getByRole("progressbar", { name: /food spent/i })).toHaveAttribute(
      "aria-valuenow",
      "80",
    );
    expect(food).toHaveTextContent("Close to the limit");
    expect(food).toHaveTextContent("RM 80.00 of RM 100.00 · RM 20.00 left");
    expect(food).toHaveTextContent(
      "At this pace about RM 165.33 by the end of the month, past the limit.",
    );
    expect(transport).toHaveTextContent("Over the limit");
    expect(transport).toHaveTextContent("RM 10.00 over");
    expect(within(transport).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
    expect(screen.getByText("Spent elsewhere").parentElement).toHaveTextContent("RM 60.00");
  });

  it("offers only categories that can have a budget and are not budgeted yet", async () => {
    render(<BudgetsScreen />, { wrapper });
    const select = await screen.findByLabelText("Category");
    await waitFor(() => expect(within(select).getAllByRole("option")).toHaveLength(2));
    expect(within(select).getByRole("option", { name: "Shopping" })).toBeInTheDocument();
    expect(within(select).queryByRole("option", { name: "Refund" })).toBeNull();
    expect(within(select).queryByRole("option", { name: "Food" })).toBeNull();
  });

  it("adds a budget, converting typed ringgit to whole sen", async () => {
    put.mockResolvedValue(ok({ category: "Shopping", limit_sen: 12550, updated_at: null }));
    render(<BudgetsScreen />, { wrapper });
    const select = await screen.findByLabelText("Category");
    await waitFor(() => within(select).getByRole("option", { name: "Shopping" }));
    await userEvent.selectOptions(select, "Shopping");
    const form = select.closest("form")!;
    await userEvent.type(within(form).getByLabelText(/monthly limit/i), "125.50");
    await userEvent.click(within(form).getByRole("button", { name: "Add budget" }));
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("/api/budgets", {
        body: { category: "Shopping", limit_sen: 12550 },
      }),
    );
  });

  it("removes a budget only after confirming", async () => {
    del.mockResolvedValue(ok(undefined, 204));
    render(<BudgetsScreen />, { wrapper });
    const list = await screen.findByRole("list", { name: /your budgets/i });
    await userEvent.click(within(list).getAllByRole("button", { name: "Remove" })[0]);
    expect(del).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("dialog", { name: /remove the food budget/i });
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith("/api/budgets", { params: { query: { category: "Food" } } }),
    );
  });

  it("suggests a budget with the working shown, and saves one on request", async () => {
    post.mockResolvedValue(ok(SUGGESTION));
    put.mockResolvedValue(ok({ category: "Food", limit_sen: 37500, updated_at: null }));
    render(<BudgetsScreen />, { wrapper });
    await userEvent.click(await screen.findByRole("button", { name: "Suggest a budget" }));
    expect(await screen.findByText("Left to budget")).toBeInTheDocument();
    expect(screen.getByText("Less a buffer (10% of income)").nextSibling).toHaveTextContent(
      "RM 100.00",
    );
    expect(screen.getByText(/3 months/)).toHaveTextContent(
      "July 2026, August 2026, September 2026",
    );
    await userEvent.click(screen.getByRole("button", { name: "Use RM 375.00 for Food" }));
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("/api/budgets", {
        body: { category: "Food", limit_sen: 37500 },
      }),
    );
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("has an empty state and an error state", async () => {
    routes({ ...BUDGET_STATUS, items: [], total_limit_sen: 0, total_spent_sen: 0 });
    const { unmount } = render(<BudgetsScreen />, { wrapper });
    expect(await screen.findByText("No budgets yet")).toBeInTheDocument();
    unmount();
    get.mockResolvedValue(fail(500, "internal_error", "Something went wrong on our side."));
    render(<BudgetsScreen />, { wrapper });
    expect(await screen.findByText("Something went wrong on our side.")).toBeInTheDocument();
  });
});
