import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SaferTiming } from "@/components/risk/SaferTiming";
import { SecondOpinion } from "@/components/risk/SecondOpinion";
import type { PlanInput, RiskCheck, Schedule } from "@/lib/api/queries";

const post = vi.fn();
vi.mock("@/lib/api/client", () => ({
  api: { GET: vi.fn(), POST: (...a: unknown[]) => post(...a) },
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

type Opinion = NonNullable<RiskCheck["second_opinion"]>;

function opinion(patch: Partial<Opinion> = {}): Opinion {
  return {
    without_probability: 0.08,
    with_probability: 0.21,
    added_probability: 0.13,
    already_at_risk: false,
    stack: [
      {
        month: "2026-10",
        by_provider: [{ provider_label: "Atome", amount_sen: 10000 }],
        new_plan_sen: 0,
        total_sen: 10000,
        known_income_sen: 120000,
      },
      {
        month: "2026-11",
        by_provider: [
          { provider_label: "Atome", amount_sen: 10000 },
          { provider_label: "Grab PayLater", amount_sen: 5000 },
        ],
        new_plan_sen: 20000,
        total_sen: 35000,
        known_income_sen: 0,
      },
    ],
    exposure: {
      unpaid_before_sen: 25000,
      unpaid_after_sen: 85000,
      providers_before: ["Atome", "Grab PayLater"],
      providers_after: ["Atome", "Grab PayLater", "SPayLater"],
      plans_before: 2,
      plans_after: 3,
      recorded_limits_sen: 160000,
      reaches_bnm_line: true,
      bnm_line_sen: 150000,
    },
    ...patch,
  };
}

describe("SecondOpinion", () => {
  it("shows the chance without, with, and what the purchase adds", () => {
    render(<SecondOpinion opinion={opinion()} />);
    const head = screen.getByRole("region", {
      name: /what this purchase adds/i,
    });
    expect(within(head).getByText("8%")).toBeInTheDocument();
    expect(within(head).getByText("21%")).toBeInTheDocument();
    expect(within(head).getByText(/\+13 points/)).toBeInTheDocument();
  });

  it("says plainly when the student is already At Risk without the purchase", () => {
    render(
      <SecondOpinion
        opinion={opinion({
          without_probability: 0.62,
          with_probability: 0.64,
          added_probability: 0.02,
          already_at_risk: true,
        })}
      />,
    );
    expect(
      screen.getByText(/already at risk without this purchase/i),
    ).toBeInTheDocument();
  });

  it("stacks every unpaid instalment by month, with this purchase and known income", () => {
    render(<SecondOpinion opinion={opinion()} />);
    const table = screen.getByRole("table", {
      name: /what you owe each month/i,
    });
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3); // header + two months
    expect(within(rows[2]).getByText("November 2026")).toBeInTheDocument();
    expect(within(rows[2]).getByText(/Atome RM 100.00/)).toBeInTheDocument();
    expect(
      within(rows[2]).getByText(/Grab PayLater RM 50.00/),
    ).toBeInTheDocument();
    expect(within(rows[2]).getByText("RM 200.00")).toBeInTheDocument();
    expect(within(rows[2]).getByText("RM 350.00")).toBeInTheDocument();
    // a month with no confirmed income says so instead of RM 0.00
    expect(within(rows[2]).getByText(/none confirmed/i)).toBeInTheDocument();
  });

  it("shows the exposure before and after, and the RM1,500 line as information", () => {
    render(<SecondOpinion opinion={opinion()} />);
    expect(screen.getByText(/RM 250.00 to RM 850.00/)).toBeInTheDocument();
    expect(screen.getByText(/2 providers to 3/)).toBeInTheDocument();
    expect(
      screen.getByText(/your recorded limits add up to RM 1,600.00/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/at or above RM 1,500.00/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/compliant|illegal|breach/i),
    ).not.toBeInTheDocument();
  });

  it("leaves out months with nothing due and no income, and says so", () => {
    const base = opinion();
    const empty = {
      month: "2026-12",
      by_provider: [],
      new_plan_sen: 0,
      total_sen: 0,
      known_income_sen: 0,
    };
    render(
      <SecondOpinion opinion={opinion({ stack: [...base.stack, empty] })} />,
    );
    const table = screen.getByRole("table", {
      name: /what you owe each month/i,
    });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(
      screen.getByText(
        /1 month with nothing due and no confirmed income is left out/i,
      ),
    ).toBeInTheDocument();
  });

  it("asks for limits instead of guessing when none are recorded", () => {
    const base = opinion();
    render(
      <SecondOpinion
        opinion={opinion({
          exposure: {
            ...base.exposure,
            recorded_limits_sen: null,
            reaches_bnm_line: null,
          },
        })}
      />,
    );
    expect(
      screen.getByText(/record your provider limits/i),
    ).toBeInTheDocument();
  });
});

const INPUT: PlanInput = {
  provider: "spaylater",
  item_name: "Headphones",
  purchase_date: "2026-10-09",
  num_installments: 3,
  total_price_sen: 60000,
  monthly_fee_rate_pct: 0,
};

function schedule(patch: Partial<Schedule> = {}): Schedule {
  return {
    status: "ok",
    without_probability: 0.08,
    already_at_risk: false,
    added_max: 0.05,
    at_risk_edge: 0.3,
    options: [
      {
        purchase_date: "2026-10-09",
        num_installments: 3,
        first_payment_date: null,
        with_probability: 0.21,
        added_probability: 0.13,
        qualifies: false,
        as_typed: true,
      },
      {
        purchase_date: "2026-10-26",
        num_installments: 6,
        first_payment_date: null,
        with_probability: 0.11,
        added_probability: 0.03,
        qualifies: true,
        as_typed: false,
      },
    ],
    chosen_index: 1,
    ...patch,
  };
}

function ok(data: unknown) {
  return { data, error: undefined, response: { ok: true, status: 200 } };
}

describe("SaferTiming", () => {
  beforeEach(() => post.mockReset());

  it("searches on request, lists what was tried and offers the first that qualifies", async () => {
    post.mockResolvedValue(ok(schedule()));
    const onUse = vi.fn();
    const user = userEvent.setup();
    render(<SaferTiming request={INPUT} onUse={onUse} />, { wrapper });

    await user.click(
      screen.getByRole("button", { name: /find a better time/i }),
    );

    expect(post.mock.calls[0][0]).toBe("/api/risk/schedule");
    expect(post.mock.calls[0][1].body).toEqual(INPUT);
    const list = await screen.findByRole("list", { name: /options tried/i });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(
      within(items[0]).getByText(/as you entered it/i),
    ).toBeInTheDocument();
    expect(within(items[0]).getByText(/\+13 points/)).toBeInTheDocument();
    expect(within(items[1]).getByText(/26 October 2026/)).toBeInTheDocument();
    expect(
      within(items[1]).queryByText(/date you entered/i),
    ).not.toBeInTheDocument();
    expect(within(items[1]).getByText(/6 instalments/)).toBeInTheDocument();
    expect(screen.getByText(/adds at most 5 points/i)).toBeInTheDocument();

    await user.click(
      within(items[1]).getByRole("button", { name: /use this/i }),
    );
    expect(onUse).toHaveBeenCalledWith({
      ...INPUT,
      purchase_date: "2026-10-26",
      num_installments: 6,
    });
  });

  it("labels another count on the same day as the date you entered", () => {
    const sameDay = { ...schedule().options[1], purchase_date: "2026-10-09" };
    render(
      <SaferTiming
        result={schedule({ options: [schedule().options[0], sameDay] })}
      />,
      {
        wrapper,
      },
    );
    expect(
      screen.getByText(/on the date you entered · 6 instalments/i),
    ).toBeInTheDocument();
  });

  it("moves a typed first payment date with the option", async () => {
    post.mockResolvedValue(
      ok(
        schedule({
          options: [
            { ...schedule().options[1], first_payment_date: "2026-11-26" },
          ],
          chosen_index: 0,
        }),
      ),
    );
    const onUse = vi.fn();
    const user = userEvent.setup();
    render(
      <SaferTiming
        request={{ ...INPUT, first_payment_date: "2026-11-09" }}
        onUse={onUse}
      />,
      { wrapper },
    );
    await user.click(
      screen.getByRole("button", { name: /find a better time/i }),
    );
    await user.click(await screen.findByRole("button", { name: /use this/i }));
    expect(onUse.mock.calls[0][0].first_payment_date).toBe("2026-11-26");
  });

  it("says honestly when no option qualified", async () => {
    post.mockResolvedValue(
      ok(schedule({ options: [schedule().options[0]], chosen_index: null })),
    );
    const user = userEvent.setup();
    render(<SaferTiming request={INPUT} onUse={vi.fn()} />, { wrapper });
    await user.click(
      screen.getByRole("button", { name: /find a better time/i }),
    );
    expect(
      await screen.findByText(/none of the 1 option we tried/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /use this/i }),
    ).not.toBeInTheDocument();
  });

  it("says why there is no suggestion when already At Risk without the purchase", async () => {
    post.mockResolvedValue(
      ok(
        schedule({
          already_at_risk: true,
          without_probability: 0.62,
          chosen_index: null,
        }),
      ),
    );
    const user = userEvent.setup();
    render(<SaferTiming request={INPUT} onUse={vi.fn()} />, { wrapper });
    await user.click(
      screen.getByRole("button", { name: /find a better time/i }),
    );
    expect(await screen.findByText(/no timing can fix/i)).toBeInTheDocument();
  });

  it("shows the locked state when history is short", async () => {
    post.mockResolvedValue(
      ok({ ...schedule(), status: "locked", options: [], chosen_index: null }),
    );
    const user = userEvent.setup();
    render(<SaferTiming request={INPUT} onUse={vi.fn()} />, { wrapper });
    await user.click(
      screen.getByRole("button", { name: /find a better time/i }),
    );
    await waitFor(() =>
      expect(screen.getByText(/needs more history/i)).toBeInTheDocument(),
    );
  });

  it("is read-only without a way to use an option (the assistant card)", () => {
    render(<SaferTiming result={schedule()} />, { wrapper });
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
