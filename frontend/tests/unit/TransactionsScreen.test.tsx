import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TransactionsScreen } from "@/components/screens/TransactionsScreen";

const get = vi.fn();
const post = vi.fn();
const patch = vi.fn();
const del = vi.fn();
vi.mock("@/lib/api/client", () => ({
  api: {
    GET: (...a: unknown[]) => get(...a),
    POST: (...a: unknown[]) => post(...a),
    PATCH: (...a: unknown[]) => patch(...a),
    DELETE: (...a: unknown[]) => del(...a),
  },
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const ROWS = [
  {
    id: "t1",
    date: "2026-10-05",
    amount_sen: 1850,
    type: "expense",
    category: "Food",
    description: "Lunch",
    account_name: null,
    is_bnpl: false,
    source: "manual",
    bnpl_plan_id: null,
    recurring_item_id: null,
  },
  {
    id: "t2",
    date: "2026-10-01",
    amount_sen: 120000,
    type: "income",
    category: "Allowance",
    description: null,
    account_name: null,
    is_bnpl: false,
    source: "csv",
    bnpl_plan_id: null,
    recurring_item_id: null,
  },
  {
    id: "t3",
    date: "2026-10-03",
    amount_sen: 5000,
    type: "expense",
    category: "BNPL",
    description: "Headphones 1/3",
    account_name: null,
    is_bnpl: true,
    source: "manual",
    bnpl_plan_id: "p1",
    recurring_item_id: null,
  },
];

function ok(data: unknown, status = 200) {
  return { data, error: undefined, response: { ok: true, status } };
}
function fail(status: number, code: string, message: string) {
  return { data: undefined, error: { detail: { code, message } }, response: { ok: false, status } };
}

const MONTHS = {
  months: [
    { month: "2026-09", income_sen: 0, spend_sen: 100, refund_sen: 0, savings_sen: 0, net_sen: -100 },
    { month: "2026-10", income_sen: 120000, spend_sen: 6850, refund_sen: 0, savings_sen: 0, net_sen: 1 },
  ],
  history: null,
};
const SPENDING = {
  month: "2026-10",
  income_sen: 120000,
  spend_sen: 6850,
  gross_spend_sen: 6850,
  refund_sen: 0,
  savings_sen: 0,
  categories: [
    { category: "BNPL", spend_sen: 5000, count: 1, share: 0.73 },
    { category: "Food", spend_sen: 1850, count: 1, share: 0.27 },
  ],
};
const PLANS = [
  {
    id: "p1",
    item_name: "Headphones",
    provider_label: "SPayLater",
    paid_count: 1,
    num_installments: 3,
  },
];
const CATEGORY_LIST = {
  categories: [
    ...["Food", "Transport", "Rent", "Salary", "Allowance", "Shopping", "Bills"].map((name) => ({
      name,
      builtin: true,
      locked: true,
      assignable: true,
      note: null,
      transaction_count: 0,
    })),
    {
      name: "BNPL",
      builtin: true,
      locked: true,
      assignable: false,
      note: "x",
      transaction_count: 1,
    },
    {
      name: "Boyfriend Tax",
      builtin: false,
      locked: false,
      assignable: true,
      note: null,
      transaction_count: 2,
    },
  ],
};

let transactions: unknown[] = ROWS;
let categoryList: () => unknown = () => ok(CATEGORY_LIST);

function route(path: string) {
  switch (path) {
    case "/api/summary/months":
      return ok(MONTHS);
    case "/api/transactions":
      return ok({ transactions, next_cursor: null });
    case "/api/summary/categories":
      return ok(SPENDING);
    case "/api/plans":
      return ok(PLANS);
    case "/api/categories":
      return categoryList();
    default:
      throw new Error(`unexpected GET ${path}`);
  }
}

function transactionQueries(): Record<string, string>[] {
  return get.mock.calls.filter((c) => c[0] === "/api/transactions").map((c) => c[1].params.query);
}

describe("TransactionsScreen", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 15));
    for (const m of [get, post, patch, del]) m.mockReset();
    transactions = ROWS;
    categoryList = () => ok(CATEGORY_LIST);
    get.mockImplementation(async (path: string) => route(path));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("lists transactions with signs, and shows a plan payment's plan instead of Edit and Delete", async () => {
    render(<TransactionsScreen />, { wrapper });

    expect(await screen.findByText("Lunch")).toBeInTheDocument();
    expect(screen.getByText("+RM 1,200.00")).toBeInTheDocument();
    expect(screen.getByText("3 transactions")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit headphones/i })).not.toBeInTheDocument();
    const box = screen.getByRole("link", { name: /managed in plans/i });
    expect(box).toHaveAttribute("href", "/plans");
    expect(within(box).getByText("SPayLater · Headphones")).toBeInTheDocument();
    expect(within(box).getByText("1 of 3 paid")).toBeInTheDocument();
  });

  it("opens on the latest month that has data and asks the server for just that month", async () => {
    render(<TransactionsScreen />, { wrapper });
    await screen.findByText("Lunch");

    expect(screen.getAllByText("October 2026").length).toBeGreaterThan(0);
    expect(transactionQueries().at(-1)).toEqual({ start: "2026-10-01", end: "2026-10-31" });
    expect(get).toHaveBeenCalledWith("/api/summary/categories", {
      params: { query: { month: "2026-10" } },
    });
  });

  it("steps back a month and loads that month, and cannot go past this month or before the first", async () => {
    render(<TransactionsScreen />, { wrapper });
    await screen.findByText("Lunch");
    expect(screen.getByRole("button", { name: /next month/i })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /previous month/i }));

    await waitFor(() =>
      expect(transactionQueries().at(-1)).toEqual({ start: "2026-09-01", end: "2026-09-30" }),
    );
    expect(screen.getByRole("button", { name: /previous month/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /next month/i })).toBeEnabled();
  });

  it("asks the server for only what the type and category say", async () => {
    render(<TransactionsScreen />, { wrapper });
    await screen.findByText("Lunch");

    await userEvent.click(screen.getByRole("button", { name: "Income" }));
    await waitFor(() =>
      expect(transactionQueries().at(-1)).toEqual({
        start: "2026-10-01",
        end: "2026-10-31",
        type: "income",
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: /clear filters/i }));
    await waitFor(() =>
      expect(transactionQueries().at(-1)).toEqual({ start: "2026-10-01", end: "2026-10-31" }),
    );
  });

  it("filters by a category picked in the spending panel, and again to let go", async () => {
    render(<TransactionsScreen />, { wrapper });
    await screen.findByText("Lunch");

    const panel = await screen.findByRole("complementary", { name: /spending this month/i });
    await userEvent.click(within(panel).getByRole("button", { name: /food/i }));

    await waitFor(() => expect(transactionQueries().at(-1)).toMatchObject({ category: "Food" }));
    expect(screen.getByLabelText("Category")).toHaveValue("Food");
    await userEvent.click(within(panel).getByRole("button", { name: /food/i }));
    await waitFor(() => expect(transactionQueries().at(-1)).not.toHaveProperty("category"));
  });

  it("narrows the list as the person types, without asking the server again", async () => {
    render(<TransactionsScreen />, { wrapper });
    await screen.findByText("Lunch");
    const before = get.mock.calls.length;

    await userEvent.type(screen.getByLabelText("Search"), "lun");

    expect(screen.getByText("Lunch")).toBeInTheDocument();
    expect(screen.queryByText("Headphones 1/3")).not.toBeInTheDocument();
    expect(screen.getByText("1 transaction")).toBeInTheDocument();
    expect(get.mock.calls.length).toBe(before);
  });

  it("says nothing matches, and offers to clear, when a search finds nothing", async () => {
    render(<TransactionsScreen />, { wrapper });
    await screen.findByText("Lunch");

    await userEvent.type(screen.getByLabelText("Search"), "zzz");

    expect(await screen.findByText("Nothing matches")).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: /clear filters/i })[0]);
    expect(await screen.findByText("Lunch")).toBeInTheDocument();
  });

  it("offers the person's own categories, and not the one plans assign", async () => {
    render(<TransactionsScreen />, { wrapper });
    await screen.findByText("Lunch");

    const filter = screen.getByLabelText("Category");

    await waitFor(() =>
      expect(within(filter).getByRole("option", { name: "Boyfriend Tax" })).toBeInTheDocument(),
    );
    expect(within(filter).getByRole("option", { name: "Food" })).toBeInTheDocument();
    expect(within(filter).queryByRole("option", { name: "BNPL" })).not.toBeInTheDocument();
  });

  it("still offers the built-in categories and what the ledger uses when the category list fails", async () => {
    categoryList = () => fail(500, "server_error", "Something went wrong on our side.");
    const own = { ...ROWS[0], id: "t4", category: "Hangout", description: "Cinema" };
    transactions = [...ROWS, own];
    render(<TransactionsScreen />, { wrapper });
    await screen.findByText("Lunch");

    const filter = screen.getByLabelText("Category");

    expect(within(filter).getByRole("option", { name: "Hangout" })).toBeInTheDocument();
    expect(within(filter).getByRole("option", { name: "Food" })).toBeInTheDocument();
  });

  it("adds a transaction, converting typed ringgit to whole sen", async () => {
    post.mockResolvedValue(ok(ROWS[0], 201));
    render(<TransactionsScreen />, { wrapper });
    await screen.findByText("Lunch");

    await userEvent.click(screen.getByRole("button", { name: /add transaction/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/amount/i), "19.99");
    await userEvent.type(within(dialog).getByLabelText(/description/i), "Parking");
    await userEvent.click(within(dialog).getByRole("button", { name: /add transaction/i }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/api/transactions");
    expect(post.mock.calls[0][1].body).toMatchObject({
      amount_sen: 1999,
      type: "expense",
      category: "Food",
      description: "Parking",
    });
  });

  it("keeps the form open and explains when the server refuses an edit", async () => {
    patch.mockResolvedValue(fail(422, "validation_error", "That date is too far in the future."));
    render(<TransactionsScreen />, { wrapper });
    await screen.findByText("Lunch");

    await userEvent.click(screen.getByRole("button", { name: /edit lunch/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /save changes/i }));

    expect(
      await within(dialog).findByText("That date is too far in the future."),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /save changes/i })).toBeEnabled();
  });

  it("deletes only after confirming", async () => {
    del.mockResolvedValue({
      data: undefined,
      error: undefined,
      response: { ok: true, status: 204 },
    });
    render(<TransactionsScreen />, { wrapper });
    await screen.findByText("Lunch");

    await userEvent.click(screen.getByRole("button", { name: /delete lunch/i }));
    expect(del).not.toHaveBeenCalled();
    await userEvent.click(await screen.findByRole("button", { name: /^delete$/i }));

    await waitFor(() => expect(del).toHaveBeenCalledTimes(1));
    expect(del.mock.calls[0][1]).toEqual({ params: { path: { transaction_id: "t1" } } });
  });

  it("shows an empty state and an error state", async () => {
    transactions = [];
    const { unmount } = render(<TransactionsScreen />, { wrapper });
    expect(await screen.findByText("Nothing here yet")).toBeInTheDocument();
    expect(screen.getByText(/nothing is logged for october 2026/i)).toBeInTheDocument();
    unmount();

    get.mockImplementation(async (path: string) =>
      path === "/api/transactions"
        ? fail(500, "server_error", "Something went wrong on our side.")
        : route(path),
    );
    render(<TransactionsScreen />, { wrapper });
    expect(await screen.findByText("Something went wrong on our side.")).toBeInTheDocument();
  });

  it("says why Save is disabled instead of just greying it out", async () => {
    render(<TransactionsScreen />, { wrapper });
    await screen.findByText("Lunch");
    await userEvent.click(screen.getByRole("button", { name: /add transaction/i }));
    const dialog = await screen.findByRole("dialog");

    const save = within(dialog).getByRole("button", { name: "Add transaction" });
    expect(save).toBeDisabled();
    expect(save).toHaveAccessibleDescription("Enter an amount greater than zero.");

    await userEvent.type(within(dialog).getByLabelText(/amount/i), "5");
    expect(save).toBeEnabled();
  });

  it("puts focus on the page heading after a delete, not on a row that no longer exists", async () => {
    del.mockResolvedValue({
      data: undefined,
      error: undefined,
      response: { ok: true, status: 204 },
    });
    render(
      <main>
        <TransactionsScreen />
      </main>,
      { wrapper },
    );
    await screen.findByText("Lunch");
    await userEvent.click(screen.getByRole("button", { name: /delete lunch/i }));
    await userEvent.click(await screen.findByRole("button", { name: /^delete$/i }));

    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1, name: "Transactions" })).toHaveFocus(),
    );
  });
});
