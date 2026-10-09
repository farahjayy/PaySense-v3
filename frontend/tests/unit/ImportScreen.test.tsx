import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ImportScreen } from "@/components/screens/ImportScreen";

const post = vi.fn();
vi.mock("@/lib/api/client", () => ({
  api: { POST: (...args: unknown[]) => post(...args), GET: vi.fn() },
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const PREVIEW = {
  rows: [
    {
      row: 2,
      date: "2026-09-01",
      amount_sen: 120000,
      type: "income",
      category_guess: "Allowance",
      description: "PTPTN",
      issues: [],
      duplicate: false,
    },
    {
      row: 3,
      date: "2026-09-03",
      amount_sen: 900,
      type: "expense",
      category_guess: "Transport",
      description: "TNG",
      issues: [],
      duplicate: true,
    },
  ],
  skipped: [{ row: 4, reason: "No amount" }],
  duplicate_count: 1,
};

function csv(name = "statement.csv", body = "date,amount\n") {
  return new File([body], name, { type: "text/csv" });
}

function ok(data: unknown) {
  return { data, error: undefined, response: { ok: true, status: 200 } };
}

describe("ImportScreen", () => {
  beforeEach(() => post.mockReset());

  it("rejects a file that is not a CSV without calling the server", async () => {
    render(<ImportScreen />, { wrapper });
    await userEvent.upload(screen.getByLabelText("Choose a CSV file"), csv("notes.txt"), {
      applyAccept: false,
    });

    expect(await screen.findByText(/choose a \.csv file/i)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("shows the server's explanation when the file cannot be read", async () => {
    post.mockResolvedValue({
      data: undefined,
      error: {
        detail: { code: "empty_file", message: "No usable rows were found." },
      },
      response: { ok: false, status: 422 },
    });
    render(<ImportScreen />, { wrapper });
    await userEvent.upload(screen.getByLabelText("Choose a CSV file"), csv());

    expect(await screen.findByText("No usable rows were found.")).toBeInTheDocument();
  });

  it("previews, leaves duplicates out, and confirms only what is ticked with edits applied", async () => {
    post.mockResolvedValueOnce(ok(PREVIEW)).mockResolvedValueOnce(ok({ created: 1 }));
    render(<ImportScreen />, { wrapper });
    await userEvent.upload(screen.getByLabelText("Choose a CSV file"), csv());

    expect(await screen.findByText(/1 row could not be read/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^include row 2/i)).toBeChecked();
    expect(screen.getByLabelText(/^include row 3/i)).not.toBeChecked();
    expect(screen.getByText(/already in your ledger/i)).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Category for row 2"), "Salary");
    await userEvent.click(screen.getByRole("button", { name: /add 1 transaction$/i }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[1][0]).toBe("/api/import/confirm");
    expect(post.mock.calls[1][1]).toEqual({
      body: {
        rows: [
          {
            date: "2026-09-01",
            amount_sen: 120000,
            type: "income",
            category: "Salary",
            description: "PTPTN",
          },
        ],
      },
    });
    const done = await screen.findByText(/1 transaction added/i);
    expect(done).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /see your dashboard/i })).toHaveAttribute("href", "/");
  });

  it("cannot confirm with nothing ticked, and says nothing was saved when the server refuses", async () => {
    post.mockResolvedValueOnce(ok(PREVIEW)).mockResolvedValueOnce({
      data: undefined,
      error: { detail: { code: "invalid", message: "Row 2 has a bad date." } },
      response: { ok: false, status: 422 },
    });
    render(<ImportScreen />, { wrapper });
    await userEvent.upload(screen.getByLabelText("Choose a CSV file"), csv());
    await screen.findByLabelText(/^include row 2/i);

    await userEvent.click(screen.getByRole("button", { name: /untick all/i }));
    expect(screen.getByRole("button", { name: /add 0 transactions/i })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /^tick all/i }));
    await userEvent.click(screen.getByRole("button", { name: /add 2 transactions/i }));

    const alert = await screen.findByText("Nothing was saved");
    expect(
      within(alert.closest("[role=alert]") as HTMLElement).getByText(/bad date/i),
    ).toBeVisible();
  });
});
