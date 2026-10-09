import { describe, expect, it } from "vitest";

import type { PlanInput, RiskCheck } from "@/lib/api/queries";
import { toPlanInput } from "@/lib/plans";
import { draftFromInput, riskNotices } from "@/lib/risk";

function check(patch: Partial<RiskCheck> = {}): RiskCheck {
  return {
    status: "ok",
    lock_reason: null,
    months_of_history: 6,
    stale_days: 2,
    unmatched_items: [],
    suspect_months: [],
    plan: {} as RiskCheck["plan"],
    probability: 0.2,
    band: "Caution",
    score: 80,
    simulated_probability: 0.22,
    probability_without_purchase: 0.1,
    factors: [],
    suggestion: null,
    repayment: {
      level: "none",
      overdue_count: 0,
      overdue_sen: 0,
      late_paid_count: 0,
      longest_miss_run: 0,
      reason: "",
    },
    with_plan_curve: null,
    without_curve: null,
    versions: null,
    check_id: null,
    ...patch,
  };
}

describe("riskNotices", () => {
  it("is silent for a fresh, complete ledger", () => {
    expect(riskNotices(check())).toEqual([]);
  });

  it("flags a stale ledger only past two weeks", () => {
    expect(riskNotices(check({ stale_days: 14 }))).toEqual([]);
    const [stale] = riskNotices(check({ stale_days: 30 }));
    expect(stale.tone).toBe("warning");
    expect(stale.body).toMatch(/30 days ago/);
  });

  it("passes on incomplete months and unmatched items with the server's wording", () => {
    const out = riskNotices(
      check({
        suspect_months: [
          { month: "2026-08", reason: "no_income", detail: "No income was logged." },
        ],
        unmatched_items: ["Rent"],
      }),
    );
    expect(out.map((n) => n.id)).toEqual(["suspect-2026-08", "unmatched"]);
    expect(out[0].title).toBe("August 2026 looks incomplete");
  });
});

describe("draftFromInput", () => {
  it("round-trips a rule-driven request through the form state", () => {
    const input: PlanInput = {
      provider: "spaylater",
      item_name: "Headphones",
      purchase_date: "2026-10-09",
      num_installments: 6,
      total_price_sen: 45000,
      monthly_fee_rate_pct: 1.5,
    };
    const provider = {
      key: "spaylater",
      label: "SPayLater",
      rule_driven: true,
      checkout_instalments: 0,
      start_rule: "months_after_purchase",
      start_offset_months: 1,
      monthly_fee_applies: true,
    } as const;
    expect(toPlanInput(draftFromInput(input, "2026-10-09"), provider)).toEqual(input);
  });

  it("round-trips a manual request, keeping which amount the person typed", () => {
    const input: PlanInput = {
      provider: "other",
      item_name: "Laptop",
      purchase_date: "2026-10-09",
      num_installments: 4,
      monthly_fee_rate_pct: 0,
      first_payment_date: "2026-11-01",
      provider_label: "Grab PayLater",
      total_payable_sen: 120000,
    };
    const provider = {
      key: "other",
      label: "Other provider",
      rule_driven: false,
      checkout_instalments: 0,
      start_rule: "purchase_date",
      start_offset_months: 0,
      monthly_fee_applies: false,
    } as const;
    expect(toPlanInput(draftFromInput(input, "2026-10-09"), provider)).toEqual(input);
  });
});
