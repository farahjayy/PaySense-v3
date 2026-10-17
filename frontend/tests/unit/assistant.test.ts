import { describe, expect, it } from "vitest";

import {
  QUICK_ACTIONS,
  SUGGESTED_PROMPTS,
  TIER_LABEL,
  actionTitle,
  addTransactionArgs,
  budgetArgs,
  checkPurchaseArgs,
  describeInputs,
  formatSource,
  stateFromError,
  toolLabel,
  trimHistory,
} from "@/lib/assistant";
import { ApiError } from "@/lib/api/queries";

describe("tiers and labels", () => {
  it("names each tier in plain words", () => {
    expect(TIER_LABEL).toEqual({
      0: "Read",
      1: "Worked out",
      2: "Needs your OK",
    });
  });

  it("turns a tool name into words", () => {
    expect(toolLabel("check_purchase_risk")).toBe("Check purchase risk");
    expect(toolLabel("get_bill_analysis")).toBe("Get bill analysis");
  });

  it("titles each kind of proposal", () => {
    expect(actionTitle("create_plan")).toBe("Add this BNPL plan?");
    expect(actionTitle("set_budget")).toBe("Save this budget?");
    expect(actionTitle("delete_budget")).toBe("Remove this budget?");
    expect(actionTitle("add_transaction")).toBe("Add this transaction?");
    expect(actionTitle("confirm_import")).toBe("Add these transactions?");
  });
});

describe("trimHistory", () => {
  it("keeps the last eight plain-text turns and drops empty ones", () => {
    const turns = Array.from({ length: 12 }, (_, i) => ({
      role: i % 2 ? ("assistant" as const) : ("user" as const),
      text: `turn ${i}`,
    }));
    const kept = trimHistory([...turns, { role: "user", text: "   " }]);
    expect(kept).toHaveLength(8);
    expect(kept[0].text).toBe("turn 4");
    expect(Object.keys(kept[0])).toEqual(["role", "text"]);
  });

  it("cuts a very long turn to the server's limit", () => {
    const [turn] = trimHistory([{ role: "user", text: "x".repeat(5000) }]);
    expect(turn.text).toHaveLength(4000);
  });
});

describe("describeInputs", () => {
  it("formats money fields as ringgit and leaves the rest readable", () => {
    expect(
      describeInputs({
        provider: "spaylater",
        total_price_sen: 79900,
        num_installments: 3,
      }),
    ).toEqual(["Provider: spaylater", "Total price: RM 799.00", "Num installments: 3"]);
  });

  it("summarises nested values instead of printing raw objects", () => {
    expect(
      describeInputs({
        rows: [{ a: 1 }, { a: 2 }],
        payload: { category: "Food" },
      }),
    ).toEqual(["Rows: 2 items", 'Payload: {"category":"Food"}']);
  });
});

describe("formatSource", () => {
  it("formats each unit", () => {
    expect(formatSource({ label: "x", value: 12000, unit: "sen", source: "t" })).toBe("RM 120.00");
    expect(
      formatSource({
        label: "x",
        value: 0.62,
        unit: "probability",
        source: "t",
      }),
    ).toBe("62%");
    expect(formatSource({ label: "x", value: 0.8, unit: "percent", source: "t" })).toBe("80%");
    expect(
      formatSource({
        label: "x",
        value: "2026-03-12",
        unit: "date",
        source: "t",
      }),
    ).toBe("12 March 2026");
    expect(formatSource({ label: "x", value: 3, unit: "count", source: "t" })).toBe("3");
    expect(formatSource({ label: "x", value: "At Risk", unit: "text", source: "t" })).toBe(
      "At Risk",
    );
  });
});

describe("stateFromError", () => {
  it("maps the server's refusals to panel states", () => {
    expect(stateFromError(new ApiError("x", 403, "consent_required"))).toBe("consent");
    expect(stateFromError(new ApiError("x", 429, "assistant_daily_budget"))).toBe("budget");
    expect(stateFromError(new ApiError("x", 429, "too_many_requests"))).toBe("rate_limited");
    expect(stateFromError(new ApiError("x", 0, "network_error"))).toBe("offline");
    expect(stateFromError(new ApiError("x", 500, "internal_error"))).toBe("error");
    expect(stateFromError(new Error("boom"))).toBe("error");
  });
});

describe("guided form builders", () => {
  it("builds a purchase check from typed ringgit", () => {
    expect(
      checkPurchaseArgs(
        {
          item: " Phone ",
          price: "799",
          provider: "spaylater",
          instalments: "3",
        },
        "2026-10-18",
      ),
    ).toEqual({
      provider: "spaylater",
      item_name: "Phone",
      purchase_date: "2026-10-18",
      num_installments: 3,
      total_price_sen: 79900,
    });
  });

  it("refuses an ambiguous price or a missing item", () => {
    const base = {
      item: "Phone",
      price: "799",
      provider: "spaylater",
      instalments: "3",
    };
    expect(checkPurchaseArgs({ ...base, price: "7.999" }, "2026-10-18")).toBeNull();
    expect(checkPurchaseArgs({ ...base, item: "  " }, "2026-10-18")).toBeNull();
    expect(checkPurchaseArgs({ ...base, instalments: "0" }, "2026-10-18")).toBeNull();
    expect(checkPurchaseArgs({ ...base, instalments: "two" }, "2026-10-18")).toBeNull();
  });

  it("builds a set-budget proposal", () => {
    expect(budgetArgs({ category: " Food ", limit: "400" })).toEqual({
      type: "set_budget",
      payload: { category: "Food", limit_sen: 40000 },
    });
    expect(budgetArgs({ category: "Food", limit: "0" })).toBeNull();
    expect(budgetArgs({ category: "", limit: "10" })).toBeNull();
  });

  it("builds an add-transaction proposal", () => {
    expect(
      addTransactionArgs(
        {
          amount: "12.50",
          type: "expense",
          category: "Food",
          description: " Nasi lemak ",
        },
        "2026-10-18",
      ),
    ).toEqual({
      type: "add_transaction",
      payload: {
        date: "2026-10-18",
        amount_sen: 1250,
        type: "expense",
        category: "Food",
        description: "Nasi lemak",
      },
    });
    expect(
      addTransactionArgs(
        { amount: "abc", type: "expense", category: "Food", description: "" },
        "2026-10-18",
      ),
    ).toBeNull();
  });
});

describe("prompts and quick actions", () => {
  it("offers the demo story and read-only quick actions", () => {
    expect(SUGGESTED_PROMPTS[0]).toMatch(/RM799 phone/);
    expect(QUICK_ACTIONS.map((q) => q.tool)).toContain("get_bill_analysis");
    expect(QUICK_ACTIONS.every((q) => !q.tool.startsWith("propose"))).toBe(true);
  });
});
