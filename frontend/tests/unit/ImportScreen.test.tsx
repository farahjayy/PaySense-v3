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
  notes: [],
  duplicate_count: 1,
};

// A file that carries its own categories, and a workbook with a sheet that was not a table.
const OWN_PREVIEW = {
  rows: [
    {
      row: 1,
      date: "2025-08-01",
      amount_sen: 680,
      type: "expense",
      category_guess: "Hangout",
      description: "Kopi Corner",
      issues: [],
      duplicate: false,
    },
    {
      row: 2,
      date: "2025-08-02",
      amount_sen: 1590,
      type: "expense",
      category_guess: "Food",
      description: "Rice Stall",
      issues: [],
      duplicate: false,
    },
  ],
  skipped: [],
  notes: ["Sheet 'Summary' was not read: no date and amount columns found."],
  duplicate_count: 0,
};

function csv(name = "statement.csv", body = "date,amount\n") {
  return new File([body], name, { type: "text/csv" });
}

function ok(data: unknown) {
  return { data, error: undefined, response: { ok: true, status: 200 } };
}

describe("ImportScreen", () => {
  beforeEach(() => post.mockReset());

  it("rejects a file that is neither CSV nor Excel without calling the server", async () => {
    render(<ImportScreen />, { wrapper });
    await userEvent.upload(screen.getByLabelText("Choose a statement file"), csv("notes.pdf"), {
      applyAccept: false,
    });

    expect(await screen.findByText(/please choose a csv or excel/i)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("offers Excel files in the file picker and sends a workbook to the server", async () => {
    post.mockResolvedValueOnce(ok(OWN_PREVIEW));
    render(<ImportScreen />, { wrapper });
    const input = screen.getByLabelText("Choose a statement file");
    expect(input).toHaveAttribute("accept", expect.stringContaining(".xlsx"));

    await userEvent.upload(input, csv("budget.xlsx", "x"));

    expect(await screen.findByLabelText(/^include row 1/i)).toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("says that only ticked rows are saved", async () => {
    post.mockResolvedValueOnce(ok(PREVIEW));
    render(<ImportScreen />, { wrapper });
    await userEvent.upload(screen.getByLabelText("Choose a statement file"), csv());

    expect(await screen.findByText(/only ticked rows are saved/i)).toBeInTheDocument();
  });

  it("keeps the file's own categories on offer in every row, even after one row is changed", async () => {
    post.mockResolvedValueOnce(ok(OWN_PREVIEW));
    render(<ImportScreen />, { wrapper });
    await userEvent.upload(screen.getByLabelText("Choose a statement file"), csv());
    const second = await screen.findByLabelText("Category for row 2");
    expect(within(second).getByRole("option", { name: "Hangout" })).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Category for row 1"), "Food");

    expect(within(second).getByRole("option", { name: "Hangout" })).toBeInTheDocument();
  });

  it("names a sheet that was not read", async () => {
    post.mockResolvedValueOnce(ok(OWN_PREVIEW));
    render(<ImportScreen />, { wrapper });
    await userEvent.upload(screen.getByLabelText("Choose a statement file"), csv());

    expect(await screen.findByText(/sheet 'summary' was not read/i)).toBeInTheDocument();
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
    await userEvent.upload(screen.getByLabelText("Choose a statement file"), csv());

    expect(await screen.findByText("No usable rows were found.")).toBeInTheDocument();
  });

  it("previews, leaves duplicates out, and confirms only what is ticked with edits applied", async () => {
    post.mockResolvedValueOnce(ok(PREVIEW)).mockResolvedValueOnce(ok({ created: 1 }));
    render(<ImportScreen />, { wrapper });
    await userEvent.upload(screen.getByLabelText("Choose a statement file"), csv());

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
    await userEvent.upload(screen.getByLabelText("Choose a statement file"), csv());
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

  it("says plainly that PDFs are not read, and what to do about a PDF statement", () => {
    render(<ImportScreen />, { wrapper });

    expect(screen.getByText(/we read csv and excel files, not pdfs/i)).toBeInTheDocument();
    expect(screen.getByText(/convert it to csv or excel first/i)).toBeInTheDocument();
  });

  it("offers the import template as a download", () => {
    render(<ImportScreen />, { wrapper });

    const link = screen.getByRole("link", { name: /download the import template/i });

    expect(link).toHaveAttribute("href", "/paysense-import-template.csv");
    expect(link).toHaveAttribute("download");
  });
});
