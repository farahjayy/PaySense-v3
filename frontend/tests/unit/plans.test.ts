import { describe, expect, it } from "vitest";

import type { ProviderInfo } from "@/lib/api/queries";
import { emptyDraft, toPlanInput, type PlanDraft } from "@/lib/plans";

const SPAYLATER: ProviderInfo = {
  key: "spaylater",
  label: "SPayLater",
  rule_driven: true,
  checkout_instalments: 0,
  start_rule: "months_after_purchase",
  start_offset_months: 1,
  monthly_fee_applies: true,
};
const TIKTOK: ProviderInfo = {
  ...SPAYLATER,
  key: "tiktok_paylater",
  label: "TikTok PayLater",
  monthly_fee_applies: false,
};
const OTHER: ProviderInfo = {
  key: "other",
  label: "Other provider",
  rule_driven: false,
  checkout_instalments: 0,
  start_rule: "purchase_date",
  start_offset_months: 0,
  monthly_fee_applies: false,
};

function draft(patch: Partial<PlanDraft>): PlanDraft {
  return { ...emptyDraft("2026-10-09"), itemName: "Headphones", ...patch };
}

describe("toPlanInput", () => {
  it("sends only the price and fee for a provider that follows its own rules", () => {
    expect(
      toPlanInput(draft({ priceSen: 30000, feePct: "1.5", instalments: "3" }), SPAYLATER),
    ).toEqual({
      provider: "spaylater",
      item_name: "Headphones",
      purchase_date: "2026-10-09",
      num_installments: 3,
      total_price_sen: 30000,
      monthly_fee_rate_pct: 1.5,
    });
  });

  it("forces the fee to zero where the provider charges none", () => {
    const input = toPlanInput(
      draft({ provider: "tiktok_paylater", priceSen: 30000, feePct: "9" }),
      TIKTOK,
    );
    expect(input?.monthly_fee_rate_pct).toBe(0);
  });

  it("sends the checkout's own numbers for another provider, never a price", () => {
    const input = toPlanInput(
      draft({
        provider: "other",
        providerLabel: "Grab PayLater",
        firstPaymentDate: "2026-11-01",
        amountMode: "total",
        amountSen: 31000,
        priceSen: 99999,
      }),
      OTHER,
    );
    expect(input).toEqual({
      provider: "other",
      item_name: "Headphones",
      purchase_date: "2026-10-09",
      num_installments: 3,
      monthly_fee_rate_pct: 0,
      first_payment_date: "2026-11-01",
      provider_label: "Grab PayLater",
      total_payable_sen: 31000,
    });
    expect(input).not.toHaveProperty("total_price_sen");
  });

  it("returns null until everything the provider needs has been entered", () => {
    expect(toPlanInput(draft({ priceSen: null }), SPAYLATER)).toBeNull();
    expect(toPlanInput(draft({ priceSen: 30000, itemName: "  " }), SPAYLATER)).toBeNull();
    expect(toPlanInput(draft({ priceSen: 30000, instalments: "0" }), SPAYLATER)).toBeNull();
    expect(toPlanInput(draft({ priceSen: 30000, instalments: "37" }), SPAYLATER)).toBeNull();
    expect(toPlanInput(draft({ priceSen: 30000, instalments: "2.5" }), SPAYLATER)).toBeNull();
    expect(toPlanInput(draft({ priceSen: 30000, feePct: "abc" }), SPAYLATER)).toBeNull();
    expect(toPlanInput(draft({ provider: "other", amountSen: 5000 }), OTHER)).toBeNull();
    expect(toPlanInput(draft({ priceSen: 30000 }), undefined)).toBeNull();
  });
});
