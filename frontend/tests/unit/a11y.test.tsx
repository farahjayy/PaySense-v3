/**
 * Automated accessibility checks (axe-core) on every screen, with data on screen. axe cannot judge
 * colour contrast in jsdom (no layout or styles), so contrast is checked through the design tokens
 * and by the screenshots in the responsive pass; everything else it can judge is enforced here.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import type { ComponentProps, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/AppShell";
import { RiskResult } from "@/components/risk/RiskResult";
import { AccountScreen } from "@/components/screens/AccountScreen";
import { BudgetsScreen } from "@/components/screens/BudgetsScreen";
import { CategoriesScreen } from "@/components/screens/CategoriesScreen";
import { InsightsScreen } from "@/components/screens/InsightsScreen";
import { DashboardScreen } from "@/components/screens/DashboardScreen";
import { ImportScreen } from "@/components/screens/ImportScreen";
import { ModelScreen } from "@/components/screens/ModelScreen";
import { PlansScreen } from "@/components/screens/PlansScreen";
import { RecurringScreen } from "@/components/screens/RecurringScreen";
import { TransactionsScreen } from "@/components/screens/TransactionsScreen";

import { SECOND_OPINION } from "./assistantFixtures";
import { BUDGET_STATUS, CONSENT, RECS } from "./topicTestUtils";

const get = vi.fn();
vi.mock("@/lib/api/client", () => ({
  api: {
    GET: (...a: unknown[]) => get(...a),
    POST: vi.fn(),
    PATCH: vi.fn(),
    DELETE: vi.fn(),
  },
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/",
}));
vi.mock("next/dynamic", () => ({ default: () => () => <div aria-hidden /> }));

const USER = {
  id: "u1",
  username: "amir",
  display_name: "Amir",
  persona: null,
} as const;

const FORECAST = {
  status: "ok",
  as_of: "2026-10-09",
  model: "lstm",
  months_of_history: 6,
  data_through: "2026-10-08",
  stale_days: 1,
  is_stale: true,
  unmatched_items: ["Rent"],
  suspect_months: [
    { month: "2026-08", reason: "no_income", detail: "No income was logged." },
  ],
  lock_reason: null,
  band: "Caution",
  health_score: 78,
  simulation: {
    months: ["2026-10"],
    monthly_margin_p10_sen: [0],
    monthly_margin_p50_sen: [1],
    monthly_margin_p90_sen: [2],
    cumulative_margin_p10_sen: [0],
    cumulative_margin_p50_sen: [1],
    cumulative_margin_p90_sen: [2],
    p_shortfall: 0.22,
    worst_month: "2026-10",
    weeks: 8,
    horizon_capped: false,
    bootstrap: "fallback",
  },
};

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
  num_installments: 2,
  purchase_date: "2026-10-01",
  first_payment_date: "2026-10-01",
  status: "overdue",
  installment_amount_sen: 15000,
  total_payable_sen: 30000,
  paid_count: 0,
  remaining_count: 2,
  next_due_date: "2026-10-01",
  risk_score_at_creation: null,
  installments: [
    {
      seq: 1,
      due_date: "2026-10-01",
      amount_sen: 15000,
      is_paid: false,
      paid_date: null,
    },
    {
      seq: 2,
      due_date: "2026-11-01",
      amount_sen: 15000,
      is_paid: false,
      paid_date: null,
    },
  ],
};

const TXN = {
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
};

const DATA: Record<string, unknown> = {
  "/api/forecast": FORECAST,
  "/api/alerts": { items: [], checked_rules: [], notes: [] },
  "/api/budgets/status": BUDGET_STATUS,
  "/api/recommendations": RECS,
  "/api/account/consent": {
    ...CONSENT,
    accepted: true,
    accepted_at: "2026-10-18T10:00:00Z",
  },
  "/api/insights/bills": {
    as_of: "2026-10-10",
    window_days: 30,
    collision_window_days: 7,
    recurring: {
      count: 0,
      monthly_total_sen: 0,
      monthly_income_sen: null,
      bills_share: null,
      items: [],
    },
    increases: [],
    collisions: [],
    upcoming: [],
    upcoming_total_sen: 0,
  },
  "/api/insights/spending": {
    month: "2026-09",
    previous_month: null,
    income_sen: 0,
    spend_sen: 1850,
    savings_sen: 0,
    left_over_sen: -1850,
    savings_rate: null,
    set_aside_rate: null,
    headline: "You spent RM 18.50 this month.",
    headline_rule: "spent",
    categories: [],
    movers: [],
    unusual: [],
    unusual_note: null,
    mad_k: 3,
  },
  "/api/bills": {
    months: [
      {
        month: "2026-10",
        is_current: true,
        total_due_sen: 15000,
        paid_total_sen: 0,
        fully_paid: false,
        has_overdue: true,
        items: [
          {
            plan_id: "p1",
            item_name: "Headphones",
            provider: "atome",
            provider_label: "Atome",
            seq: 1,
            amount_sen: 15000,
            due_date: "2026-10-01",
            is_paid: false,
          },
        ],
      },
    ],
  },
  "/api/summary/months": {
    months: [
      {
        month: "2026-09",
        income_sen: 1,
        spend_sen: 2,
        refund_sen: 0,
        savings_sen: 0,
        net_sen: -1,
      },
    ],
    history: null,
  },
  "/api/transactions": { transactions: [TXN], next_cursor: null },
  "/api/summary/categories": {
    month: "2026-09",
    income_sen: 1,
    spend_sen: 1850,
    gross_spend_sen: 1850,
    refund_sen: 0,
    savings_sen: 0,
    categories: [{ category: "Food", spend_sen: 1850, count: 1, share: 1 }],
  },
  "/api/categories": {
    categories: [
      {
        name: "Food",
        builtin: true,
        locked: true,
        assignable: true,
        note: null,
        transaction_count: 1,
      },
      {
        name: "Refund",
        builtin: true,
        locked: true,
        assignable: true,
        note: "Money back.",
        transaction_count: 0,
      },
      {
        name: "BNPL",
        builtin: true,
        locked: true,
        assignable: false,
        note: "Added by plans.",
        transaction_count: 0,
      },
      {
        name: "Gym",
        builtin: false,
        locked: false,
        assignable: true,
        note: null,
        transaction_count: 2,
      },
    ],
  },
  "/api/plans": [PLAN],
  "/api/providers": [],
  "/api/model-info": {
    forecast: { model: "lstm", version: "v1" },
    risk: {
      available: true,
      version: "v1",
      family: "lightgbm",
      development_profiles: 9000,
      lockbox_brier: 0.0198,
      constant_brier: 0.1788,
      feature_schema_hash: "2066b37e13182a5e",
    },
  },
  "/api/provider-limits": [
    {
      provider: "atome",
      limit_sen: 50000,
      used_sen: 30000,
      remaining_sen: 20000,
    },
  ],
  "/api/recurring-items": [
    {
      id: "r1",
      kind: "bill",
      name: "Rent",
      match_text: "rent",
      amount_sen: 40000,
      cadence: "monthly",
      custom_interval_days: null,
      anchor_date: "2026-09-01",
      active: false,
      origin: "manual",
    },
  ],
  "/api/recurring-items/suggestions": [
    {
      name: "netflix",
      display_name: "Netflix",
      kind: "bill",
      amount_sen: 3500,
      cadence: "monthly",
      anchor_date: "2026-09-15",
      confidence: 0.9,
      occurrences: 4,
    },
  ],
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

async function violations(container: HTMLElement) {
  const result = await axe.run(container, {
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  return result.violations.map(
    (v) => `${v.id}: ${v.nodes.map((n) => n.html).join(" | ")}`,
  );
}

const SCREENS: [string, ReactNode, string][] = [
  ["dashboard", <DashboardScreen key="d" />, "Caution"],
  ["transactions", <TransactionsScreen key="t" />, "Lunch"],
  ["categories", <CategoriesScreen key="c" />, "Gym"],
  ["recurring", <RecurringScreen key="r" />, "Netflix"],
  ["plans", <PlansScreen key="p" />, "Headphones"],
  ["import", <ImportScreen key="i" />, "Choose a file"],
  ["model", <ModelScreen key="m" />, "gradient-boosted trees"],
  ["budgets", <BudgetsScreen key="b" />, "Close to the limit"],
  ["insights", <InsightsScreen key="n" />, "Transport is over budget"],
  ["account", <AccountScreen key="a" />, "You accepted version"],
];

describe("accessibility (axe)", () => {
  beforeEach(() => {
    get.mockReset();
    get.mockImplementation(async (path: string) => ({
      data: DATA[path] ?? [],
      error: undefined,
      response: { ok: true, status: 200 },
    }));
  });

  it.each(SCREENS)(
    "%s has no detectable violations",
    async (_name, screenNode, ready) => {
      const { container } = render(
        <AppShell user={USER}>{screenNode}</AppShell>,
        { wrapper },
      );
      await screen.findAllByText(new RegExp(ready, "i"));
      expect(await violations(container)).toEqual([]);
    },
  );

  it("an open dialog (add transaction) has no detectable violations", async () => {
    const { container } = render(<TransactionsScreen />, { wrapper });
    await screen.findByText("Lunch");
    await userEvent.click(
      screen.getByRole("button", { name: "Add transaction" }),
    );
    await screen.findByRole("dialog");
    expect(await violations(container)).toEqual([]);
  });

  it("a risk result with reasons, a suggestion, the second opinion and a repayment warning has no detectable violations", async () => {
    const plan: ComponentProps<typeof RiskResult>["check"]["plan"] = {
      provider: "spaylater",
      provider_label: "SPayLater",
      schedule_source: "provider_rule",
      total_price_sen: 60000,
      financed_sen: 60000,
      upfront_sen: 0,
      total_payable_sen: 60000,
      fee_sen: 0,
      total_cost_sen: 60000,
      cash_at_purchase_sen: 0,
      monthly_fee_rate_pct: 0,
      num_installments: 2,
      purchase_date: "2026-10-09",
      first_payment_date: "2026-11-09",
      limit_known: false,
      remaining_limit_sen: null,
      installments: [
        {
          seq: 1,
          due_date: "2026-11-09",
          amount_sen: 30000,
          paid_at_checkout: false,
        },
        {
          seq: 2,
          due_date: "2026-12-09",
          amount_sen: 30000,
          paid_at_checkout: false,
        },
      ],
    };
    const curve = {
      months: ["2026-10", "2026-11"],
      cumulative_p10_sen: [-5000, -20000],
      cumulative_p50_sen: [20000, 35000],
      cumulative_p90_sen: [40000, 80000],
    };
    const { container } = render(
      <RiskResult
        onTrySuggestion={() => {}}
        request={{
          provider: "spaylater",
          item_name: "Phone",
          purchase_date: "2026-10-09",
          num_installments: 2,
          total_price_sen: 60000,
          monthly_fee_rate_pct: 0,
        }}
        check={{
          status: "ok",
          lock_reason: null,
          months_of_history: 6,
          stale_days: 30,
          unmatched_items: [],
          suspect_months: [],
          plan,
          probability: 0.42,
          band: "At Risk",
          score: 58,
          simulated_probability: 0.45,
          simulated_band: "At Risk",
          probability_without_purchase: 0.1,
          factors: [
            {
              feature: "dsr_with_purchase",
              text: "About 40% of income.",
              contribution: 0.08,
            },
          ],
          suggestion: {
            status: "found",
            basis: "model",
            changes: [
              { kind: "instalments", label: "Spread it over 6 instalments" },
            ],
            probability: 0.07,
            band: "Safe",
            request: null,
            evaluated: 3,
          },
          repayment: {
            level: "warning",
            overdue_count: 3,
            overdue_sen: 15000,
            late_paid_count: 0,
            longest_miss_run: 3,
            reason: "Three missed in a row.",
          },
          with_plan_curve: curve,
          without_curve: curve,
          versions: { model: "m", feature_schema_hash: "h" },
          check_id: null,
          second_opinion: { ...SECOND_OPINION, already_at_risk: true },
        }}
      />,
      { wrapper },
    );
    expect(await violations(container)).toEqual([]);
  });
});
