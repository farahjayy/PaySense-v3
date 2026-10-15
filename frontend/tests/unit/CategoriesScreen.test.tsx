import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CategoriesScreen } from "@/components/screens/CategoriesScreen";

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

function entry(name: string, over: Record<string, unknown> = {}) {
  return {
    name,
    builtin: true,
    locked: true,
    assignable: true,
    note: null,
    transaction_count: 0,
    ...over,
  };
}

const LIST = {
  categories: [
    entry("Food", { transaction_count: 12 }),
    entry("Other"),
    entry("Refund", { note: "Money back for a purchase. It is taken off your spending." }),
    entry("Transfer", { note: "A move between your own accounts. It is left out." }),
    entry("BNPL", { assignable: false, note: "Added by your BNPL plans.", transaction_count: 3 }),
    entry("Boyfriend Tax", { builtin: false, locked: false, transaction_count: 2 }),
    entry("Gym", { builtin: false, locked: false, transaction_count: 0 }),
  ],
};

function ok(data: unknown, status = 200) {
  return { data, error: undefined, response: { ok: true, status } };
}
function fail(status: number, code: string, message: string) {
  return { data: undefined, error: { detail: { code, message } }, response: { ok: false, status } };
}

describe("CategoriesScreen", () => {
  beforeEach(() => {
    for (const m of [get, post, patch, del]) m.mockReset();
    get.mockResolvedValue(ok(LIST));
  });

  it("lists the person's own categories with how many transactions use each", async () => {
    render(<CategoriesScreen />, { wrapper });

    const own = await screen.findByRole("list", { name: /your categories/i });
    const rows = within(own).getAllByRole("listitem");
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringContaining("Boyfriend Tax"),
      expect.stringContaining("Gym"),
    ]);
    expect(rows[0]).toHaveTextContent("2 transactions");
    expect(rows[1]).toHaveTextContent("No transactions");
    expect(within(rows[0]).getByRole("button", { name: /rename boyfriend tax/i })).toBeEnabled();
    expect(within(rows[0]).getByRole("button", { name: /delete boyfriend tax/i })).toBeEnabled();
  });

  it("shows the built-in categories as fixed, with why the ones the forecast depends on are", async () => {
    render(<CategoriesScreen />, { wrapper });

    const builtIn = await screen.findByRole("list", { name: /built-in categories/i });
    const rows = within(builtIn).getAllByRole("listitem");
    expect(rows).toHaveLength(5);
    for (const row of rows) {
      expect(within(row).queryByRole("button")).not.toBeInTheDocument();
      expect(within(row).getByText("Fixed")).toBeInTheDocument();
    }
    expect(within(builtIn).getByText(/taken off your spending/i)).toBeInTheDocument();
    expect(within(builtIn).getByText(/added by your bnpl plans/i)).toBeInTheDocument();
  });

  it("offers the import template as a download", async () => {
    render(<CategoriesScreen />, { wrapper });
    await screen.findByRole("list", { name: /your categories/i });

    const link = screen.getByRole("link", { name: /download import template/i });

    expect(link).toHaveAttribute("href", "/paysense-import-template.csv");
    expect(link).toHaveAttribute("download");
  });

  it("adds a category and closes the form", async () => {
    post.mockResolvedValue(ok(entry("Zakat", { builtin: false, locked: false }), 201));
    render(<CategoriesScreen />, { wrapper });
    await screen.findByRole("list", { name: /your categories/i });

    await userEvent.click(screen.getByRole("button", { name: /add category/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText(/name/i)).toHaveFocus();
    await userEvent.type(within(dialog).getByLabelText(/name/i), "Zakat");
    await userEvent.click(within(dialog).getByRole("button", { name: /^add category$/i }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0]).toEqual(["/api/categories", { body: { name: "Zakat" } }]);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("will not add a blank name, and says why", async () => {
    render(<CategoriesScreen />, { wrapper });
    await screen.findByRole("list", { name: /your categories/i });

    await userEvent.click(screen.getByRole("button", { name: /add category/i }));
    const dialog = await screen.findByRole("dialog");

    const add = within(dialog).getByRole("button", { name: /^add category$/i });
    expect(add).toBeDisabled();
    expect(add).toHaveAccessibleDescription("Type a name for the category.");
  });

  it("keeps the form open and explains when the server says the name is taken", async () => {
    post.mockResolvedValue(
      fail(409, "category_exists", "A category with that name already exists."),
    );
    render(<CategoriesScreen />, { wrapper });
    await screen.findByRole("list", { name: /your categories/i });

    await userEvent.click(screen.getByRole("button", { name: /add category/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/name/i), "food");
    await userEvent.click(within(dialog).getByRole("button", { name: /^add category$/i }));

    expect(
      await within(dialog).findByText("A category with that name already exists."),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("renames a category, starting from its current name", async () => {
    patch.mockResolvedValue(
      ok({ category: entry("Selfcare", { builtin: false, locked: false }), moved: 2 }),
    );
    render(<CategoriesScreen />, { wrapper });
    await screen.findByRole("list", { name: /your categories/i });

    await userEvent.click(screen.getByRole("button", { name: /rename boyfriend tax/i }));
    const dialog = await screen.findByRole("dialog");
    const field = within(dialog).getByLabelText(/new name/i);
    expect(field).toHaveValue("Boyfriend Tax");
    await userEvent.clear(field);
    await userEvent.type(field, "Selfcare");
    await userEvent.click(within(dialog).getByRole("button", { name: /save name/i }));

    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    expect(patch.mock.calls[0]).toEqual([
      "/api/categories",
      { body: { name: "Boyfriend Tax", new_name: "Selfcare" } },
    ]);
  });

  it("deletes a category nothing uses after one confirmation", async () => {
    del.mockResolvedValue(ok({ moved: 0 }));
    render(<CategoriesScreen />, { wrapper });
    await screen.findByRole("list", { name: /your categories/i });

    await userEvent.click(screen.getByRole("button", { name: /delete gym/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByLabelText(/move/i)).not.toBeInTheDocument();
    expect(del).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    await waitFor(() => expect(del).toHaveBeenCalledTimes(1));
    expect(del.mock.calls[0]).toEqual(["/api/categories", { params: { query: { name: "Gym" } } }]);
  });

  it("makes the person choose where a used category's transactions go before it can be deleted", async () => {
    del.mockResolvedValue(ok({ moved: 2 }));
    render(<CategoriesScreen />, { wrapper });
    await screen.findByRole("list", { name: /your categories/i });

    await userEvent.click(screen.getByRole("button", { name: /delete boyfriend tax/i }));
    const dialog = await screen.findByRole("dialog");
    const choose = within(dialog).getByLabelText(/move its 2 transactions to/i);
    const options = within(choose).getAllByRole("option").map((o) => o.textContent);
    // Refund and Transfer change how a row counts, so spending is never moved into them
    expect(options).toEqual(["Choose a category…", "Food", "Other", "Gym"]);
    expect(within(dialog).getByRole("button", { name: /^delete$/i })).toBeDisabled();

    await userEvent.selectOptions(choose, "Food");
    await userEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    await waitFor(() => expect(del).toHaveBeenCalledTimes(1));
    expect(del.mock.calls[0][1]).toEqual({
      params: { query: { name: "Boyfriend Tax", move_to: "Food" } },
    });
  });

  it("says so when the person has none of their own yet", async () => {
    get.mockResolvedValue(ok({ categories: LIST.categories.filter((c) => c.builtin) }));
    render(<CategoriesScreen />, { wrapper });

    expect(await screen.findByText(/no categories of your own yet/i)).toBeInTheDocument();
  });

  it("explains a failure to load and lets the person retry", async () => {
    get.mockResolvedValueOnce(fail(500, "server_error", "Something went wrong on our side."));
    render(<CategoriesScreen />, { wrapper });

    expect(await screen.findByText("Something went wrong on our side.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});
