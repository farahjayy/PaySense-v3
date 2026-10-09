import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RecurringScreen } from "@/components/screens/RecurringScreen";

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

const ITEM = {
  id: "r1",
  kind: "bill",
  name: "Rent",
  match_text: "rent",
  amount_sen: 40000,
  cadence: "monthly",
  custom_interval_days: null,
  anchor_date: "2026-09-01",
  active: true,
  origin: "manual",
};

const SUGGESTION = {
  name: "netflix",
  display_name: "Netflix",
  kind: "bill",
  amount_sen: 3500,
  cadence: "monthly",
  anchor_date: "2026-09-15",
  confidence: 0.92,
  occurrences: 4,
};

function ok(data: unknown, status = 200) {
  return { data, error: undefined, response: { ok: true, status } };
}

function serve({ items = [ITEM], suggestions = [SUGGESTION], unmatched = [] as string[] } = {}) {
  get.mockImplementation(async (path: string) => {
    if (path === "/api/recurring-items") return ok(items);
    if (path === "/api/recurring-items/suggestions") return ok(suggestions);
    return ok({ unmatched_items: unmatched, status: "locked", months_of_history: 0 });
  });
}

describe("RecurringScreen", () => {
  beforeEach(() => {
    for (const m of [get, post, patch, del]) m.mockReset();
  });

  it("confirms a suggestion in one tap, keeping its merchant text so renaming never unlinks it", async () => {
    serve();
    post.mockResolvedValue(ok({ ...ITEM, id: "r2", name: "Netflix" }, 201));
    render(<RecurringScreen />, { wrapper });

    await userEvent.click(await screen.findByRole("button", { name: "Confirm Netflix" }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/api/recurring-items");
    expect(post.mock.calls[0][1].body).toEqual({
      kind: "bill",
      name: "Netflix",
      amount_sen: 3500,
      cadence: "monthly",
      anchor_date: "2026-09-15",
      active: true,
      origin: "detected",
      match_text: "netflix",
    });
  });

  it("lists items, pauses one, and deletes one", async () => {
    serve({ suggestions: [] });
    patch.mockResolvedValue(ok({ ...ITEM, active: false }));
    del.mockResolvedValue({
      data: undefined,
      error: undefined,
      response: { ok: true, status: 204 },
    });
    render(<RecurringScreen />, { wrapper });

    expect(await screen.findByText("Rent")).toBeInTheDocument();
    expect(screen.getByText("RM 400.00")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Pause Rent" }));
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    expect(patch.mock.calls[0][1].body).toEqual({ active: false });

    await userEvent.click(screen.getByRole("button", { name: "Delete Rent" }));
    await waitFor(() => expect(del).toHaveBeenCalledTimes(1));
  });

  it("adds an item by hand, rejecting a name with no letters", async () => {
    serve({ items: [], suggestions: [] });
    post.mockResolvedValue(ok(ITEM, 201));
    render(<RecurringScreen />, { wrapper });
    expect(await screen.findByText("No recurring items yet")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Add an item" }));
    const dialog = await screen.findByRole("dialog");
    const add = within(dialog).getByRole("button", { name: "Add" });
    await userEvent.type(within(dialog).getByLabelText(/amount/i), "400");
    await userEvent.type(within(dialog).getByLabelText(/^name/i), "123");
    expect(add).toBeDisabled();

    await userEvent.clear(within(dialog).getByLabelText(/^name/i));
    await userEvent.type(within(dialog).getByLabelText(/^name/i), "Rent");
    expect(add).toBeEnabled();
    await userEvent.click(add);

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][1].body).toMatchObject({
      kind: "bill",
      name: "Rent",
      amount_sen: 40000,
      cadence: "monthly",
      origin: "manual",
    });
  });

  it("points out confirmed items that matched nothing in the ledger", async () => {
    serve({ suggestions: [], unmatched: ["Rent"] });
    render(<RecurringScreen />, { wrapper });

    expect(await screen.findByText(/matched nothing in your ledger/i)).toBeInTheDocument();
  });
});
