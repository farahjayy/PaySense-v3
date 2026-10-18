import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RiskReportScreen } from "@/components/screens/RiskReportScreen";
import { RiskScreen } from "@/components/screens/RiskScreen";

const get = vi.fn();
const post = vi.fn();
vi.mock("@/lib/api/client", () => ({
  api: {
    GET: (...a: unknown[]) => get(...a),
    POST: (...a: unknown[]) => post(...a),
  },
}));
vi.mock("next/dynamic", () => ({
  default: () =>
    function Chart() {
      return <div data-testid="with-without-chart" />;
    },
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
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
];

const PLAN = {
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
  num_installments: 3,
  purchase_date: "2026-10-09",
  first_payment_date: "2026-11-09",
  limit_known: false,
  remaining_limit_sen: null,
  installments: [
    {
      seq: 1,
      due_date: "2026-11-09",
      amount_sen: 20000,
      paid_at_checkout: false,
    },
    {
      seq: 2,
      due_date: "2026-12-09",
      amount_sen: 20000,
      paid_at_checkout: false,
    },
    {
      seq: 3,
      due_date: "2027-01-09",
      amount_sen: 20000,
      paid_at_checkout: false,
    },
  ],
};

const CURVE = {
  months: ["2026-10", "2026-11"],
  cumulative_p10_sen: [-5000, -20000],
  cumulative_p50_sen: [20000, 35000],
  cumulative_p90_sen: [40000, 80000],
};

const REPAYMENT = {
  level: "none",
  overdue_count: 0,
  overdue_sen: 0,
  late_paid_count: 0,
  longest_miss_run: 0,
  reason: "No late or overdue instalments in the last six months.",
};

function result(patch: Record<string, unknown> = {}) {
  return {
    status: "ok",
    lock_reason: null,
    months_of_history: 6,
    stale_days: 1,
    unmatched_items: [],
    suspect_months: [],
    plan: PLAN,
    probability: 0.42,
    band: "At Risk",
    score: 58,
    simulated_probability: 0.45,
    simulated_band: "At Risk",
    probability_without_purchase: 0.1,
    factors: [
      {
        feature: "dsr_with_purchase",
        text: "With this plan, about 40% of your monthly income would go on BNPL and similar repayments.",
        contribution: 0.08,
      },
    ],
    suggestion: {
      status: "found",
      basis: "model",
      changes: [{ kind: "instalments", label: "Spread it over 6 instalments" }],
      probability: 0.07,
      band: "Safe",
      request: {
        provider: "spaylater",
        item_name: "Headphones",
        purchase_date: "2026-10-09",
        num_installments: 6,
        total_price_sen: 60000,
        monthly_fee_rate_pct: 0,
        // the API sends every optional field, null when unused
        first_payment_date: null,
        provider_label: null,
        instalment_sen: null,
        total_payable_sen: null,
      },
      evaluated: 3,
    },
    repayment: REPAYMENT,
    with_plan_curve: CURVE,
    without_curve: { ...CURVE, cumulative_p50_sen: [30000, 60000] },
    versions: { model: "m1", feature_schema_hash: "abc" },
    check_id: null,
    ...patch,
  };
}

function ok(data: unknown, status = 200) {
  return { data, error: undefined, response: { ok: true, status } };
}

async function fillForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(
    await screen.findByLabelText(/what are you buying/i),
    "Headphones",
  );
  await user.clear(screen.getByLabelText(/number of instalments/i));
  await user.type(screen.getByLabelText(/number of instalments/i), "3");
  await user.type(screen.getByLabelText(/^price/i), "600");
}

describe("RiskScreen", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    get.mockImplementation(async () => ok(PROVIDERS));
  });

  it("will not run until the purchase is filled in", async () => {
    render(<RiskScreen />, { wrapper });
    expect(
      await screen.findByRole("button", { name: "Check this purchase" }),
    ).toBeDisabled();
    expect(screen.getByText(/fill in the purchase/i)).toBeInTheDocument();
  });

  it("shows the band, the reasons, the suggestion, the chart and the repayment note separately", async () => {
    post.mockResolvedValue(ok(result()));
    const user = userEvent.setup();
    render(<RiskScreen />, { wrapper });
    await fillForm(user);
    await user.click(
      screen.getByRole("button", { name: "Check this purchase" }),
    );

    expect(
      await screen.findByRole("img", { name: /score 58 out of 100, at risk/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/about 40% of your monthly income/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/estimated chance of running short: 42%/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/a direct simulation of this purchase gives 45%/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Spread it over 6 instalments"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("with-without-chart")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /your repayment history/i }),
    ).toBeInTheDocument();
    expect(post.mock.calls[0][0]).toBe("/api/risk/check");
    expect(post.mock.calls[0][1].body).toMatchObject({
      provider: "spaylater",
      item_name: "Headphones",
      num_installments: 3,
      total_price_sen: 60000,
    });
  });

  it("says nothing stands out when no reason qualified, and no single change when none was found", async () => {
    post.mockResolvedValue(
      ok(
        result({
          factors: [],
          suggestion: {
            status: "none_found",
            basis: "model",
            changes: [],
            probability: null,
            band: null,
            request: null,
            evaluated: 60,
          },
        }),
      ),
    );
    const user = userEvent.setup();
    render(<RiskScreen />, { wrapper });
    await fillForm(user);
    await user.click(
      screen.getByRole("button", { name: "Check this purchase" }),
    );

    expect(
      await screen.findByText(/nothing in your numbers stands out/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no single change gets this to safe/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/we tried 60 combinations/i)).toBeInTheDocument();
  });

  it("applies a suggested change to the form and checks again", async () => {
    post.mockResolvedValueOnce(ok(result())).mockResolvedValueOnce(
      ok(
        result({
          probability: 0.07,
          band: "Safe",
          score: 93,
          suggestion: {
            status: "already_safe",
            basis: "model",
            changes: [],
            probability: null,
            band: null,
            request: null,
            evaluated: 1,
          },
        }),
      ),
    );
    const user = userEvent.setup();
    render(<RiskScreen />, { wrapper });
    await fillForm(user);
    await user.click(
      screen.getByRole("button", { name: "Check this purchase" }),
    );
    await user.click(await screen.findByRole("button", { name: "Try this" }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[1][1].body.num_installments).toBe(6);
    expect(screen.getByLabelText(/number of instalments/i)).toHaveValue("6");
    expect(
      await screen.findByRole("img", { name: /score 93 out of 100, safe/i }),
    ).toBeInTheDocument();
    // and the new result counts as current: no "you have changed" notice, going ahead is allowed
    expect(
      screen.queryByText(/you have changed the purchase/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Add this as a plan" }),
    ).toBeEnabled();
  });

  it("dims the result and disables going ahead once the form has moved on", async () => {
    post.mockResolvedValue(ok(result()));
    const user = userEvent.setup();
    render(<RiskScreen />, { wrapper });
    await fillForm(user);
    await user.click(
      screen.getByRole("button", { name: "Check this purchase" }),
    );
    await screen.findByRole("img", { name: /score 58/i });

    await user.type(screen.getByLabelText(/what are you buying/i), " 2");

    expect(
      screen.getByText(/you have changed the purchase/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Add this as a plan" }),
    ).toBeDisabled();
  });

  it("adds the plan on confirmation and links to the saved report", async () => {
    post.mockImplementation(async (path: string) =>
      path === "/api/risk/check"
        ? ok(result())
        : ok(
            {
              check_id: "11111111-1111-1111-1111-111111111111",
              check: result(),
              plan: {},
            },
            201,
          ),
    );
    const user = userEvent.setup();
    render(<RiskScreen />, { wrapper });
    await fillForm(user);
    await user.click(
      screen.getByRole("button", { name: "Check this purchase" }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Add this as a plan" }),
    );

    expect(await screen.findByText("Plan added")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /saved report/i })).toHaveAttribute(
      "href",
      "/risk/11111111-1111-1111-1111-111111111111",
    );
    expect(post.mock.calls.at(-1)?.[0]).toBe("/api/risk/confirm");
  });

  it("shows the locked state, with no number and no way to go ahead, when history is short", async () => {
    post.mockResolvedValue(
      ok(
        result({
          status: "locked",
          lock_reason: "needs_four_months",
          months_of_history: 2,
          probability: null,
          band: null,
          score: null,
          simulated_probability: null,
          probability_without_purchase: null,
          factors: [],
          suggestion: null,
          with_plan_curve: null,
          without_curve: null,
          versions: null,
        }),
      ),
    );
    const user = userEvent.setup();
    render(<RiskScreen />, { wrapper });
    await fillForm(user);
    await user.click(
      screen.getByRole("button", { name: "Check this purchase" }),
    );

    expect(
      await screen.findByText(/unlocks with four months/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Add this as a plan" }),
    ).not.toBeInTheDocument();
  });

  it("explains a failed check and a refused confirmation", async () => {
    post.mockResolvedValueOnce({
      data: undefined,
      error: {
        detail: {
          code: "risk_check_unavailable",
          message: "The risk check is not available right now.",
        },
      },
      response: { ok: false, status: 503 },
    });
    const user = userEvent.setup();
    render(<RiskScreen />, { wrapper });
    await fillForm(user);
    await user.click(
      screen.getByRole("button", { name: "Check this purchase" }),
    );

    expect(
      await screen.findByText("The risk check is not available right now."),
    ).toBeInTheDocument();
  });
});

describe("RiskScreen: the Second-Opinion Check (D-57)", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    get.mockImplementation(async () => ok(PROVIDERS));
  });

  it("finds a safer time and checks the purchase again with it", async () => {
    const schedule = {
      status: "ok",
      without_probability: 0.1,
      already_at_risk: false,
      added_max: 0.05,
      at_risk_edge: 0.3,
      options: [
        {
          purchase_date: "2026-10-26",
          num_installments: 6,
          first_payment_date: null,
          with_probability: 0.12,
          added_probability: 0.02,
          qualifies: true,
          as_typed: false,
        },
      ],
      chosen_index: 0,
    };
    post.mockImplementation(async (path: string) =>
      path === "/api/risk/schedule" ? ok(schedule) : ok(result()),
    );
    const user = userEvent.setup();
    render(<RiskScreen />, { wrapper });
    await fillForm(user);
    await user.click(
      screen.getByRole("button", { name: "Check this purchase" }),
    );
    await user.click(
      await screen.findByRole("button", { name: /find a better time/i }),
    );
    await user.click(await screen.findByRole("button", { name: /use this/i }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
    expect(post.mock.calls[1][0]).toBe("/api/risk/schedule");
    expect(post.mock.calls[2][0]).toBe("/api/risk/check");
    expect(post.mock.calls[2][1].body).toMatchObject({
      purchase_date: "2026-10-26",
      num_installments: 6,
    });
    expect(screen.getByLabelText(/number of instalments/i)).toHaveValue("6");
    expect(
      screen.queryByText(/you have changed the purchase/i),
    ).not.toBeInTheDocument();
  });
});

describe("RiskReportScreen", () => {
  beforeEach(() => get.mockReset());

  it("shows a saved report as it was, with no way to act on it", async () => {
    get.mockResolvedValue(ok(result({ check_id: "abc" })));
    render(<RiskReportScreen id="abc" />, { wrapper });

    expect(
      await screen.findByRole("img", { name: /score 58 out of 100/i }),
    ).toBeInTheDocument();
    expect(get.mock.calls[0][1]).toEqual({
      params: { path: { check_id: "abc" } },
    });
    expect(
      screen.queryByRole("button", { name: "Try this" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Add this as a plan" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /find a better time/i }),
    ).not.toBeInTheDocument();
  });

  it("says plainly when there is no such report", async () => {
    get.mockResolvedValue({
      data: undefined,
      error: {
        detail: {
          code: "risk_check_not_found",
          message: "No such risk check.",
        },
      },
      response: { ok: false, status: 404 },
    });
    render(<RiskReportScreen id="nope" />, { wrapper });

    expect(await screen.findByText("No such report")).toBeInTheDocument();
    expect(
      screen.getByText(/does not exist, or it belongs to another account/i),
    ).toBeInTheDocument();
  });
});

describe("RiskResult explanation of the two numbers", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    get.mockImplementation(async () => ok(PROVIDERS));
  });

  async function show(patch: Record<string, unknown>) {
    post.mockResolvedValue(ok(result(patch)));
    const user = userEvent.setup();
    render(<RiskScreen />, { wrapper });
    await fillForm(user);
    await user.click(
      screen.getByRole("button", { name: "Check this purchase" }),
    );
    await screen.findByRole("img", { name: /out of 100/i });
  }

  it("explains what the second number is and which one decides the band", async () => {
    await show({});
    expect(
      screen.getByText(/the estimate decides the band/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/slower, direct calculation/i)).toBeInTheDocument();
  });

  it("says plainly when the two methods put the purchase in different bands", async () => {
    await show({
      band: "Safe",
      score: 93,
      probability: 0.07,
      simulated_probability: 0.35,
      simulated_band: "At Risk",
    });
    expect(screen.getByText(/different bands/i)).toBeInTheDocument();
    expect(screen.getByText(/close to the line/i)).toBeInTheDocument();
  });

  it("does not raise that notice when they agree", async () => {
    await show({});
    expect(screen.queryByText(/different bands/i)).not.toBeInTheDocument();
  });

  it("says when waiting was judged by the simulation because the model cannot see timing", async () => {
    await show({
      suggestion: {
        status: "found",
        basis: "simulation",
        changes: [
          {
            kind: "wait",
            label: "Buy it on 2 June 2026, after your next income",
          },
        ],
        probability: 0.04,
        band: "Safe",
        request: null,
        evaluated: 5,
      },
    });
    expect(
      screen.getByText(/judged by a direct simulation/i),
    ).toBeInTheDocument();
  });
});
