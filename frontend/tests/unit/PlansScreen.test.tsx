import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PlansScreen } from "@/components/screens/PlansScreen";

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

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const PROVIDERS = [
  {
    key: "spaylater",
    label: "SPayLater",
    rule_driven: true,
    checkout_instalments: 0,
    start_rule: "months_after_purchase",
    start_offset_months: 1,
    monthly_fee_applies: true,
  },
  {
    key: "other",
    label: "Other provider",
    rule_driven: false,
    checkout_instalments: 0,
    start_rule: "purchase_date",
    start_offset_months: 0,
    monthly_fee_applies: false,
  },
];

const PLAN = {
  id: "p1",
  item_name: "Headphones",
  provider: "atome",
  provider_label: "Atome",
  schedule_source: "provider_rule",
  total_price_sen: 30000,
  financed_sen: 30000,
  upfront_sen: 0,
  monthly_fee_rate_pct: 0,
  num_installments: 3,
  purchase_date: "2026-10-01",
  first_payment_date: "2026-10-01",
  status: "active",
  installment_amount_sen: 10000,
  total_payable_sen: 30000,
  paid_count: 1,
  remaining_count: 2,
  next_due_date: "2026-11-01",
  risk_score_at_creation: null,
  installments: [
    { seq: 1, due_date: "2026-10-01", amount_sen: 10000, is_paid: true, paid_date: "2026-10-01" },
    { seq: 2, due_date: "2026-11-01", amount_sen: 10000, is_paid: false, paid_date: null },
    { seq: 3, due_date: "2026-12-01", amount_sen: 10000, is_paid: false, paid_date: null },
  ],
};

const LIMITS = [
  { provider: "spaylater", limit_sen: 20000, used_sen: 0, remaining_sen: 20000 },
  { provider: "tiktok_paylater", limit_sen: null, used_sen: 0, remaining_sen: null },
  { provider: "atome", limit_sen: null, used_sen: 0, remaining_sen: null },
];

// The author's example: a RM300 purchase against a RM200 limit leaves RM100 to pay at checkout.
const PREVIEW = {
  provider: "spaylater",
  provider_label: "SPayLater",
  schedule_source: "provider_rule",
  total_price_sen: 30000,
  financed_sen: 20000,
  upfront_sen: 10000,
  total_payable_sen: 20000,
  cash_at_purchase_sen: 10000,
  monthly_fee_rate_pct: 0,
  num_installments: 2,
  purchase_date: "2026-10-09",
  first_payment_date: "2026-11-09",
  limit_known: true,
  remaining_limit_sen: 20000,
  installments: [
    { seq: 1, due_date: "2026-11-09", amount_sen: 10000, paid_at_checkout: false },
    { seq: 2, due_date: "2026-12-09", amount_sen: 10000, paid_at_checkout: false },
  ],
};

function ok(data: unknown, status = 200) {
  return { data, error: undefined, response: { ok: true, status } };
}

function serve(plans: unknown[] = [PLAN]) {
  get.mockImplementation(async (path: string) => {
    if (path === "/api/plans") return ok(plans);
    if (path === "/api/providers") return ok(PROVIDERS);
    if (path === "/api/provider-limits") return ok(LIMITS);
    return ok([]);
  });
}

describe("PlansScreen", () => {
  beforeEach(() => {
    for (const m of [get, post, put, del]) m.mockReset();
  });

  it("lists plans with progress and the next due date", async () => {
    serve();
    render(<PlansScreen />, { wrapper });

    expect(await screen.findByText("Headphones")).toBeInTheDocument();
    expect(screen.getByText(/1 of 3 paid/)).toBeInTheDocument();
    expect(screen.getByText(/next due 1 November 2026/)).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("marks one instalment paid, and several at once", async () => {
    serve();
    post.mockResolvedValue(ok({}));
    render(<PlansScreen />, { wrapper });
    await screen.findByText("Headphones");

    await userEvent.click(screen.getByRole("button", { name: /show instalments/i }));
    await userEvent.click(
      screen.getByRole("button", { name: /mark paid, instalment 2 of headphones/i }),
    );
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/api/plans/{plan_id}/installments/{seq}/pay");
    expect(post.mock.calls[0][1].params.path).toEqual({ plan_id: "p1", seq: 2 });

    await userEvent.click(screen.getByRole("button", { name: /mark all 2 as paid/i }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[1][0]).toBe("/api/plans/{plan_id}/pay");
    expect(post.mock.calls[1][1].body).toEqual({ seqs: [2, 3] });
  });

  it("shows the server's split live: RM300 on a RM200 limit means RM100 at checkout, then saves", async () => {
    serve([]);
    post.mockImplementation(async (path: string) =>
      path === "/api/plans/preview" ? ok(PREVIEW) : ok({ ...PLAN, id: "p2" }, 201),
    );
    render(<PlansScreen />, { wrapper });
    await screen.findByText("No plans yet");

    await userEvent.click(screen.getAllByRole("button", { name: "Add a plan" })[0]);
    const dialog = await screen.findByRole("dialog");
    const save = within(dialog).getByRole("button", { name: "Save plan" });
    expect(save).toBeDisabled();

    await userEvent.type(within(dialog).getByLabelText(/what are you buying/i), "Phone case");
    await userEvent.clear(within(dialog).getByLabelText(/number of instalments/i));
    await userEvent.type(within(dialog).getByLabelText(/number of instalments/i), "2");
    await userEvent.type(within(dialog).getByLabelText(/^price/i), "300");

    const checkout = await within(dialog).findByText("Pay at checkout", {}, { timeout: 3000 });
    expect(checkout.closest("div")).toHaveTextContent("RM 100.00");
    expect(within(dialog).getByText(/part of this is paid up front/i)).toBeInTheDocument();
    const previewCall = post.mock.calls.find((c) => c[0] === "/api/plans/preview");
    expect(previewCall?.[1].body).toMatchObject({
      provider: "spaylater",
      item_name: "Phone case",
      num_installments: 2,
      total_price_sen: 30000,
    });

    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);
    await waitFor(() => expect(post.mock.calls.some((c) => c[0] === "/api/plans")).toBe(true));
  });

  it("records a provider limit in sen", async () => {
    serve();
    put.mockResolvedValue(
      ok({ provider: "atome", limit_sen: 50000, used_sen: 0, remaining_sen: 50000 }),
    );
    render(<PlansScreen />, { wrapper });

    await userEvent.type(await screen.findByRole("textbox", { name: /atome limit/i }), "500");
    await userEvent.click(screen.getByRole("button", { name: /save atome limit/i }));

    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put.mock.calls[0][1]).toEqual({
      params: { path: { provider: "atome" } },
      body: { limit_sen: 50000 },
    });
  });

  it("asks before deleting a plan and passes the keep-payments choice", async () => {
    serve();
    del.mockResolvedValue({
      data: undefined,
      error: undefined,
      response: { ok: true, status: 204 },
    });
    render(<PlansScreen />, { wrapper });
    await screen.findByText("Headphones");

    await userEvent.click(screen.getByRole("button", { name: "Delete plan, Headphones" }));
    expect(del).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("checkbox"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete plan" }));

    await waitFor(() => expect(del).toHaveBeenCalledTimes(1));
    expect(del.mock.calls[0][1]).toEqual({
      params: { path: { plan_id: "p1" }, query: { keep_payments: false } },
    });
  });

  it("starts every plan deletion with the payments kept, whatever the last one chose", async () => {
    serve([PLAN, { ...PLAN, id: "p2", item_name: "Keyboard" }]);
    render(<PlansScreen />, { wrapper });
    await screen.findByText("Headphones");

    await userEvent.click(screen.getByRole("button", { name: "Delete plan, Headphones" }));
    let dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("checkbox"));
    expect(within(dialog).getByRole("checkbox")).not.toBeChecked();
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep the plan" }));

    await userEvent.click(screen.getByRole("button", { name: "Delete plan, Keyboard" }));
    dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("checkbox")).toBeChecked();
  });
});
