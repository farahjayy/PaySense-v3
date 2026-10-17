import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

export function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

export function ok(data: unknown, status = 200) {
  return { data, error: undefined, response: { ok: true, status } };
}

export function fail(status: number, code: string, message: string) {
  return { data: undefined, error: { detail: { code, message } }, response: { ok: false, status } };
}

export const BUDGET_STATUS = {
  month: "2026-10",
  is_current: true,
  days_in_month: 31,
  days_elapsed: 15,
  items: [
    {
      category: "Food",
      limit_sen: 10000,
      spent_sen: 8000,
      remaining_sen: 2000,
      percent: 0.8,
      state: "near",
      projected_sen: 16533,
      projected_state: "over",
    },
    {
      category: "Transport",
      limit_sen: 5000,
      spent_sen: 6000,
      remaining_sen: -1000,
      percent: 1.2,
      state: "over",
      projected_sen: null,
      projected_state: null,
    },
  ],
  total_limit_sen: 15000,
  total_spent_sen: 14000,
  refund_sen: 0,
  month_spend_sen: 20000,
  unbudgeted_spend_sen: 6000,
  near_at: 0.8,
  over_at: 1,
};

export const SUGGESTION = {
  month: "2026-10",
  income_sen: 100000,
  income_basis: "recurring",
  bills_sen: 30000,
  instalments_sen: 10000,
  buffer_sen: 10000,
  buffer_rate: 0.1,
  pool_sen: 50000,
  months_used: ["2026-07", "2026-08", "2026-09"],
  items: [
    { category: "Food", share: 0.75, recent_monthly_sen: 30000, limit_sen: 37500 },
    { category: "Shopping", share: 0.25, recent_monthly_sen: 10000, limit_sen: 12500 },
  ],
  notes: [],
};

export const RECS = {
  items: [
    {
      is_alert: true,
      rule: "budget_over",
      priority: 2,
      severity: "high",
      title: "Transport is over budget",
      detail: "You have spent RM 60.00 of your RM 50.00 Transport budget this month.",
      sources: [
        { label: "Spent", value: 6000, unit: "sen", source: "get_budget_status" },
        { label: "Limit", value: 5000, unit: "sen", source: "get_budget_status" },
      ],
      action: {
        kind: "link",
        label: "Review budgets",
        href: "/budgets",
        action_type: null,
        payload: null,
      },
    },
    {
      is_alert: false,
      rule: "spending_up",
      priority: 7,
      severity: "low",
      title: "Shopping spending rose RM 100.00",
      detail:
        "In September 2026 you spent RM 300.00 on Shopping, against RM 200.00 the month before.",
      sources: [
        { label: "Month before", value: 20000, unit: "sen", source: "get_spending_insights" },
      ],
      action: {
        kind: "propose",
        label: "Set a Shopping budget of RM 200.00",
        href: null,
        action_type: "set_budget",
        payload: { category: "Shopping", limit_sen: 20000 },
      },
    },
  ],
  checked_rules: ["a", "b", "c", "d", "e", "f", "g", "h", "i"],
  notes: [],
};

export const CONSENT = {
  version: "v1",
  accepted: false,
  accepted_at: null,
  sections: [
    { title: "What PaySense keeps", text: "Your username and your transactions." },
    { title: "What the assistant sends", text: "Figures are sent to Google (Gemini API)." },
  ],
};
