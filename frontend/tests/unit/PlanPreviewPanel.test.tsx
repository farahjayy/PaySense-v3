import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PlanPreviewPanel } from "@/components/plans/PlanPreviewPanel";
import type { PlanPreview } from "@/lib/api/queries";

// The author's own case: a RM3,500 camera on SPayLater over 6 instalments at 3% a month, with
// RM2,300 of limit left. The fee counts against the limit, so RM1,949.15 is financed and the
// other RM1,550.85 is paid at checkout: RM1,949.15 + 18% = RM2,300.00 in instalments.
const CAMERA: PlanPreview = {
  provider: "spaylater",
  provider_label: "SPayLater",
  schedule_source: "provider_rule",
  total_price_sen: 350000,
  financed_sen: 194915,
  upfront_sen: 155085,
  total_payable_sen: 230000,
  fee_sen: 35085,
  total_cost_sen: 385085,
  cash_at_purchase_sen: 155085,
  monthly_fee_rate_pct: 3,
  num_installments: 6,
  purchase_date: "2026-10-15",
  first_payment_date: "2026-11-15",
  limit_known: true,
  remaining_limit_sen: 230000,
  installments: [
    "2026-11-15",
    "2026-12-15",
    "2027-01-15",
    "2027-02-15",
    "2027-03-15",
    "2027-04-15",
  ].map((due_date, i) => ({
    seq: i + 1,
    due_date,
    amount_sen: i === 5 ? 38335 : 38333,
    paid_at_checkout: false,
  })),
};

function figure(label: string) {
  const term = screen.getByText(label);
  return term.closest("div") as HTMLElement;
}

describe("PlanPreviewPanel", () => {
  it("says who pays what: you now, the provider for you, and all the instalments", () => {
    render(<PlanPreviewPanel preview={CAMERA} />);

    expect(figure("You pay now")).toHaveTextContent("RM 1,550.85");
    expect(figure("SPayLater pays the shop")).toHaveTextContent("RM 1,949.15");
    expect(figure("All 6 instalments")).toHaveTextContent("RM 2,300.00");
  });

  it("shows the fee and the total cost, and how much more than the price that is", () => {
    render(<PlanPreviewPanel preview={CAMERA} />);

    const cost = screen.getByRole("group", { name: /what this costs/i });
    expect(within(cost).getByText("SPayLater fee")).toBeInTheDocument();
    expect(within(cost).getByText("RM 350.85")).toBeInTheDocument();
    expect(within(cost).getByText(/3% a month for 6 months/)).toBeInTheDocument();
    expect(within(cost).getByText("Total cost of this purchase")).toBeInTheDocument();
    expect(within(cost).getByText("RM 3,850.85")).toBeInTheDocument();
    expect(within(cost).getByText(/RM 350.85 more than the RM 3,500.00 price/)).toBeInTheDocument();
  });

  it("explains why part is paid up front, and that the fee counts against the limit", () => {
    render(<PlanPreviewPanel preview={CAMERA} />);

    const note = screen.getByText(/part of this is paid up front/i).closest("div") as HTMLElement;
    expect(note).toHaveTextContent("Your recorded SPayLater limit has RM 2,300.00 left");
    expect(note).toHaveTextContent("the fee counts against it");
    expect(note).toHaveTextContent("RM 1,949.15");
    expect(note).toHaveTextContent("RM 1,550.85");
  });

  it("lists every instalment with its date and amount", () => {
    render(<PlanPreviewPanel preview={CAMERA} />);

    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(6);
    expect(rows[0]).toHaveTextContent("1. 15 November 2026");
    expect(rows[0]).toHaveTextContent("RM 383.33");
    expect(rows[5]).toHaveTextContent("RM 383.35");
  });

  it("has no up-front note and no fee line when the whole price is financed and there is no fee", () => {
    render(
      <PlanPreviewPanel
        preview={{
          ...CAMERA,
          total_price_sen: 30000,
          financed_sen: 30000,
          upfront_sen: 0,
          total_payable_sen: 30000,
          fee_sen: 0,
          total_cost_sen: 30000,
          cash_at_purchase_sen: 0,
          monthly_fee_rate_pct: 0,
          remaining_limit_sen: null,
          limit_known: false,
          num_installments: 3,
          installments: CAMERA.installments.slice(0, 3),
        }}
      />,
    );

    expect(screen.queryByText(/part of this is paid up front/i)).not.toBeInTheDocument();
    expect(screen.queryByText("SPayLater fee")).not.toBeInTheDocument();
    // with no fee, what the provider pays, all the instalments and the total cost are one RM300.00
    expect(screen.getAllByText("RM 300.00")).toHaveLength(3);
    expect(screen.getByText(/record your spaylater limit below/i)).toBeInTheDocument();
  });

  it("does not count Atome's first instalment, paid at checkout, twice", () => {
    render(
      <PlanPreviewPanel
        preview={{
          ...CAMERA,
          provider: "atome",
          provider_label: "Atome",
          total_price_sen: 30000,
          financed_sen: 30000,
          upfront_sen: 0,
          total_payable_sen: 30000,
          fee_sen: 0,
          total_cost_sen: 30000,
          cash_at_purchase_sen: 10000,
          monthly_fee_rate_pct: 0,
          limit_known: false,
          remaining_limit_sen: null,
          num_installments: 3,
          installments: [
            { seq: 1, due_date: "2026-10-15", amount_sen: 10000, paid_at_checkout: true },
            { seq: 2, due_date: "2026-11-15", amount_sen: 10000, paid_at_checkout: false },
            { seq: 3, due_date: "2026-12-15", amount_sen: 10000, paid_at_checkout: false },
          ],
        }}
      />,
    );

    expect(figure("You pay now")).toHaveTextContent("RM 100.00");
    expect(figure("All 3 instalments")).toHaveTextContent("RM 300.00");
    expect(screen.getByText("Total cost of this purchase").closest("div")).toHaveTextContent(
      "RM 300.00",
    );
    expect(screen.getByText("at checkout")).toBeInTheDocument();
    // the tiles must not read as RM100 + RM300 for a RM300 item
    expect(screen.getByText("includes your first instalment")).toBeInTheDocument();
    expect(screen.getByText("includes the one you pay now")).toBeInTheDocument();
  });

  it("names the provider the person typed for a manual one, and shows no fee it cannot know", () => {
    render(
      <PlanPreviewPanel
        preview={{
          ...CAMERA,
          provider: "other",
          provider_label: "Grab PayLater",
          schedule_source: "manual",
          financed_sen: 10001,
          upfront_sen: 0,
          total_payable_sen: 10001,
          fee_sen: 0,
          total_cost_sen: 10001,
          total_price_sen: 10001,
          cash_at_purchase_sen: 0,
          monthly_fee_rate_pct: 0,
          num_installments: 3,
          installments: CAMERA.installments.slice(0, 3),
        }}
      />,
    );

    expect(screen.getByText("Grab PayLater pays the shop")).toBeInTheDocument();
    expect(screen.queryByText("Grab PayLater fee")).not.toBeInTheDocument();
  });
});
