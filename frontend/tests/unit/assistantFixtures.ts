/** Server-shaped assistant responses for the WP5 tests (types from the generated schema). */
import type { components } from "@/lib/api/schema";
import type { ChatCard, ChatReply, PendingAction } from "@/lib/assistant";

type Schemas = components["schemas"];

export const PREVIEW: Schemas["PlanPreviewOut"] = {
  provider: "spaylater",
  provider_label: "SPayLater",
  schedule_source: "provider_rule",
  total_price_sen: 79900,
  financed_sen: 79900,
  upfront_sen: 0,
  total_payable_sen: 79900,
  fee_sen: 0,
  total_cost_sen: 79900,
  cash_at_purchase_sen: 0,
  monthly_fee_rate_pct: 0,
  num_installments: 3,
  purchase_date: "2025-12-29",
  first_payment_date: "2026-01-29",
  limit_known: false,
  remaining_limit_sen: null,
  installments: [
    {
      seq: 1,
      due_date: "2026-01-29",
      amount_sen: 26634,
      paid_at_checkout: false,
    },
    {
      seq: 2,
      due_date: "2026-02-28",
      amount_sen: 26633,
      paid_at_checkout: false,
    },
    {
      seq: 3,
      due_date: "2026-03-29",
      amount_sen: 26633,
      paid_at_checkout: false,
    },
  ],
};

export const SECOND_OPINION: NonNullable<
  Schemas["RiskCheckOut"]["second_opinion"]
> = {
  without_probability: 0.04,
  with_probability: 0.09,
  added_probability: 0.05,
  already_at_risk: false,
  stack: [
    {
      month: "2025-12",
      by_provider: [{ provider_label: "Atome", amount_sen: 10000 }],
      new_plan_sen: 0,
      total_sen: 10000,
      known_income_sen: 120000,
    },
    {
      month: "2026-01",
      by_provider: [],
      new_plan_sen: 26633,
      total_sen: 26633,
      known_income_sen: 0,
    },
  ],
  exposure: {
    unpaid_before_sen: 10000,
    unpaid_after_sen: 89900,
    providers_before: ["Atome"],
    providers_after: ["Atome", "SPayLater"],
    plans_before: 1,
    plans_after: 2,
    recorded_limits_sen: null,
    reaches_bnm_line: null,
    bnm_line_sen: 150000,
  },
};

export const SCHEDULE: Schemas["ScheduleOut"] = {
  status: "ok",
  without_probability: 0.04,
  already_at_risk: false,
  added_max: 0.05,
  at_risk_edge: 0.3,
  options: [
    {
      purchase_date: "2025-12-29",
      num_installments: 3,
      first_payment_date: null,
      with_probability: 0.09,
      without_probability: 0.04,
      added_probability: 0.05,
      qualifies: true,
      as_typed: true,
    },
  ],
  chosen_index: 0,
  chosen: null, // set below to options[0]
};
SCHEDULE.chosen = SCHEDULE.options[0] ?? null;

export const RISK: Schemas["RiskCheckOut"] = {
  status: "ok",
  lock_reason: null,
  months_of_history: 6,
  stale_days: 1,
  unmatched_items: [],
  suspect_months: [],
  plan: PREVIEW,
  probability: 0.92,
  band: "At Risk",
  score: 8,
  simulated_probability: 0.9,
  simulated_band: "At Risk",
  probability_without_purchase: 0.67,
  factors: [
    {
      feature: "instalment_to_income",
      text: "Each instalment is about RM 266.",
      contribution: 0.2,
    },
  ],
  suggestion: {
    status: "none_found",
    basis: "model",
    changes: [],
    probability: null,
    band: null,
    request: null,
    evaluated: 20,
  },
  repayment: {
    level: "none",
    overdue_count: 0,
    overdue_sen: 0,
    late_paid_count: 0,
    longest_miss_run: 0,
    reason: "No missed payments.",
  },
  with_plan_curve: null,
  without_curve: null,
  versions: { model: "v1", feature_schema_hash: "abc" },
  check_id: null,
  second_opinion: SECOND_OPINION,
};

export const LOCKED_RISK: Schemas["RiskCheckOut"] = {
  ...RISK,
  status: "locked",
  lock_reason: "needs_four_months",
  months_of_history: 2,
  probability: null,
  band: null,
  score: null,
  simulated_probability: null,
  simulated_band: null,
  probability_without_purchase: null,
  factors: [],
  suggestion: null,
  versions: null,
};

export const CARDS: ChatCard[] = [
  { kind: "risk", title: "Risk check: Phone", data: RISK },
  {
    kind: "forecast",
    title: "Your three-month forecast",
    data: {
      status: "ok",
      as_of: "2025-12-29",
      model: "lstm",
      months_of_history: 6,
      data_through: "2025-12-28",
      stale_days: 1,
      is_stale: false,
      unmatched_items: [],
      suspect_months: [],
      lock_reason: null,
      simulation: {
        months: ["2026-01"],
        monthly_margin_p10_sen: [0],
        monthly_margin_p50_sen: [1],
        monthly_margin_p90_sen: [2],
        cumulative_margin_p10_sen: [0],
        cumulative_margin_p50_sen: [1],
        cumulative_margin_p90_sen: [2],
        p_shortfall: 0.67,
        worst_month: "2026-01",
        weeks: 13,
        horizon_capped: false,
        bootstrap: "paths",
      },
      band: "At Risk",
      health_score: 33,
    },
  },
  {
    kind: "month_summary",
    title: "Income and spending by month",
    data: {
      months: [
        {
          month: "2025-11",
          income_sen: 118969,
          spend_sen: 89336,
          refund_sen: 0,
          savings_sen: 0,
          net_sen: 29633,
        },
      ],
      history: null,
    },
  },
  {
    kind: "category_spending",
    title: "Where 2025-11's money went",
    data: {
      month: "2025-11",
      income_sen: 1,
      spend_sen: 2,
      gross_spend_sen: 2,
      refund_sen: 0,
      savings_sen: 0,
      categories: [
        { category: "Food", spend_sen: 26293, count: 30, share: 0.3 },
      ],
    },
  },
  {
    kind: "transactions",
    title: "Recent transactions",
    data: {
      transactions: [
        {
          id: "t1",
          date: "2025-12-28",
          amount_sen: 1250,
          type: "expense",
          category: "Food",
          description: "Nasi lemak",
          account_name: null,
          is_bnpl: false,
          source: "manual",
          bnpl_plan_id: null,
          recurring_item_id: null,
        },
      ],
      limit: 5,
      descriptions_redacted: false,
    },
  },
  {
    kind: "bills",
    title: "Instalments by month",
    data: {
      months: [
        {
          month: "2026-01",
          is_current: true,
          total_due_sen: 26634,
          paid_total_sen: 0,
          fully_paid: false,
          has_overdue: false,
          items: [
            {
              plan_id: "p1",
              item_name: "Phone",
              provider: "spaylater",
              provider_label: "SPayLater",
              seq: 1,
              amount_sen: 26634,
              due_date: "2026-01-29",
              is_paid: false,
            },
          ],
        },
      ],
    },
  },
  {
    kind: "bill_analysis",
    title: "Your bills and what is due",
    data: {
      as_of: "2025-12-29",
      window_days: 30,
      collision_window_days: 7,
      recurring: {
        count: 1,
        monthly_total_sen: 35160,
        monthly_income_sen: 100000,
        bills_share: 0.35,
        items: [],
      },
      increases: [
        {
          item_id: "i1",
          name: "Unifi",
          previous_sen: 9900,
          latest_sen: 10900,
          change_sen: 1000,
          change_pct: 0.1,
          previous_date: "2025-11-20",
          latest_date: "2025-12-20",
        },
      ],
      collisions: [
        {
          start: "2026-01-01",
          end: "2026-01-07",
          total_sen: 36851,
          items: [
            {
              kind: "bill",
              name: "Rent",
              due_date: "2026-01-01",
              amount_sen: 35160,
              overdue: false,
              provider_label: null,
              plan_id: null,
              seq: null,
              item_id: "r",
            },
            {
              kind: "bill",
              name: "Astro",
              due_date: "2026-01-03",
              amount_sen: 1691,
              overdue: false,
              provider_label: null,
              plan_id: null,
              seq: null,
              item_id: "a",
            },
          ],
        },
      ],
      upcoming: [
        {
          kind: "instalment",
          name: "Shoes",
          due_date: "2025-12-20",
          amount_sen: 6000,
          overdue: true,
          provider_label: "Atome",
          plan_id: "p",
          seq: 1,
          item_id: null,
        },
      ],
      upcoming_total_sen: 42851,
    },
  },
  {
    kind: "spending_insights",
    title: "How 2025-11 went",
    data: {
      month: "2025-11",
      previous_month: "2025-10",
      income_sen: 118969,
      spend_sen: 89336,
      savings_sen: 0,
      left_over_sen: 29633,
      savings_rate: 0.2491,
      set_aside_rate: 0,
      headline: "You kept 25% of your income this month.",
      headline_rule: "kept_income",
      categories: [],
      movers: [
        {
          category: "Food",
          spend_sen: 26293,
          previous_sen: 32552,
          change_sen: -6259,
          change_pct: -0.19,
          status: "down",
        },
      ],
      unusual: [
        {
          transaction_id: "u1",
          date: "2025-11-14",
          category: "Shopping",
          description: "Mall",
          amount_sen: 25000,
          median_sen: 3000,
          threshold_sen: 9000,
        },
      ],
      unusual_note: "Not enough history yet to judge Gym.",
      mad_k: 3,
    },
  },
  {
    kind: "plans",
    title: "Your BNPL plans",
    data: { plans: [] },
  },
  { kind: "plan_preview", title: "Plan preview: Phone", data: PREVIEW },
  {
    kind: "providers",
    title: "Providers and your limits",
    data: {
      providers: [
        {
          key: "spaylater",
          label: "SPayLater",
          rule_driven: true,
          checkout_instalments: 0,
          start_rule: "months_after_purchase",
          start_offset_months: 1,
          monthly_fee_applies: true,
        },
      ],
      limits: [
        {
          provider: "spaylater",
          limit_sen: 150000,
          used_sen: 26634,
          remaining_sen: 123366,
        },
      ],
    },
  },
  {
    kind: "budgets",
    title: "Your budgets",
    data: {
      budgets: [{ category: "Food", limit_sen: 40000, updated_at: null }],
    },
  },
  {
    kind: "budget_status",
    title: "Budgets for 2025-12",
    data: {
      month: "2025-12",
      is_current: true,
      days_in_month: 31,
      days_elapsed: 29,
      total_limit_sen: 40000,
      total_spent_sen: 42000,
      refund_sen: 0,
      month_spend_sen: 80000,
      unbudgeted_spend_sen: 38000,
      near_at: 0.8,
      over_at: 1,
      items: [
        {
          category: "Food",
          limit_sen: 40000,
          spent_sen: 42000,
          remaining_sen: -2000,
          percent: 1.05,
          state: "over",
          projected_sen: 44896,
          projected_state: "over",
        },
      ],
    },
  },
  {
    kind: "budget_suggestion",
    title: "Suggested budgets for 2025-12",
    data: {
      month: "2025-12",
      income_sen: 116269,
      income_basis: "recurring",
      bills_sen: 44920,
      instalments_sen: 0,
      buffer_sen: 11627,
      buffer_rate: 0.1,
      pool_sen: 59722,
      months_used: ["2025-09"],
      items: [
        {
          category: "Food",
          share: 0.49,
          recent_monthly_sen: 29398,
          limit_sen: 29000,
        },
      ],
      notes: ["A note."],
    },
  },
  {
    kind: "alerts",
    title: "Needs your attention",
    data: {
      checked_rules: ["budget_over"],
      notes: [],
      items: [
        {
          is_alert: true,
          rule: "budget_over",
          priority: 2,
          severity: "high",
          title: "Food is over budget",
          detail:
            "You have spent RM 420.00 of your RM 400.00 Food budget this month.",
          sources: [
            {
              label: "Spent",
              value: 42000,
              unit: "sen",
              source: "get_budget_status",
            },
          ],
          action: {
            kind: "link",
            label: "Review budgets",
            href: "/budgets",
            action_type: null,
            payload: null,
          },
        },
      ],
    },
  },
  {
    kind: "paste_preview",
    title: "Transactions from your paste",
    data: {
      rows: [
        {
          date: "2025-12-27",
          amount_sen: 1500,
          type: "expense",
          category: "Transport",
          description: "Grab ride",
          duplicate: true,
        },
      ],
      rejected: [
        { index: 1, reason: "RM 9.99 is not written in the pasted text." },
      ],
      duplicate_count: 1,
    },
  },
  { kind: "schedule", title: "Safer timing: Phone", data: SCHEDULE },
];

export const BUDGET_ACTION: PendingAction = {
  id: "a1",
  type: "set_budget",
  status: "pending",
  summary: "Set the Food budget to RM 400.00 a month.",
  expires_at: "2025-12-29T10:10:00Z",
  payload: { category: "Food", limit_sen: 40000 },
};

export const PLAN_ACTION: PendingAction = {
  id: "a2",
  type: "create_plan",
  status: "pending",
  summary: "Create a SPayLater plan for Phone: RM 799.00 in 3 instalment(s).",
  expires_at: "2025-12-29T10:10:00Z",
  payload: {
    provider: "spaylater",
    item_name: "Phone",
    purchase_date: "2025-12-29",
    num_installments: 3,
    total_price_sen: 79900,
    monthly_fee_rate_pct: 0,
  },
  preview: PREVIEW,
};

export function reply(overrides: Partial<ChatReply> = {}): ChatReply {
  return {
    reply: "Here is what I found.",
    mode: "llm",
    provider: "fake",
    model: "fake-1",
    steps: [],
    cards: [],
    pending_actions: [],
    narration_replaced: false,
    refused: false,
    ...overrides,
  };
}
