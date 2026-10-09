import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

describe("TransactionsScreen", () => {
  beforeEach(() => {
    for (const m of [get, post, patch, del]) m.mockReset();
    get.mockResolvedValue(ok(ROWS));
  });

  it("lists transactions with signs, and sends plan payments to Plans instead of editing them", async () => {
    render(<TransactionsScreen />, { wrapper });

    expect(await screen.findByText("Lunch")).toBeInTheDocument();
    expect(screen.getByText("+RM 1,200.00")).toBeInTheDocument();
    expect(screen.getByText("3 transactions")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit headphones/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /managed in plans/i })).toHaveAttribute(
      "href",
      "/plans",
    );
  });

  it("asks the server for only what the filters say", async () => {
    render(<TransactionsScreen />, { wrapper });
    await screen.findByText("Lunch");

    await userEvent.selectOptions(screen.getByLabelText("Type"), "income");

    await waitFor(() =>
      expect(get).toHaveBeenLastCalledWith("/api/transactions", {
        params: { query: { type: "income" } },
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: /clear filters/i }));
    await waitFor(() =>
      expect(get).toHaveBeenLastCalledWith("/api/transactions", { params: { query: {} } }),
    );
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
    get.mockResolvedValueOnce(ok([]));
    const { unmount } = render(<TransactionsScreen />, { wrapper });
    expect(await screen.findByText("Nothing here yet")).toBeInTheDocument();
    unmount();

    get.mockResolvedValueOnce(fail(500, "server_error", "Something went wrong on our side."));
    render(<TransactionsScreen />, { wrapper });
    expect(await screen.findByText("Something went wrong on our side.")).toBeInTheDocument();
  });
});
