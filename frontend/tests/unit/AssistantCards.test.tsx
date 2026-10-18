import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  AssistantMessage,
  StepsList,
} from "@/components/assistant/AssistantMessage";
import { ConfirmCard } from "@/components/assistant/ConfirmCard";
import { ResultCard } from "@/components/assistant/ResultCard";

import {
  BUDGET_ACTION,
  CARDS,
  LOCKED_RISK,
  PLAN_ACTION,
  reply,
} from "./assistantFixtures";

const post = vi.fn();
vi.mock("@/lib/api/client", () => ({
  api: { GET: vi.fn(), POST: (...a: unknown[]) => post(...a) },
}));
vi.mock("next/dynamic", () => ({ default: () => () => <div aria-hidden /> }));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

async function violations(container: HTMLElement) {
  const result = await axe.run(container, {
    rules: { "color-contrast": { enabled: false } },
  });
  return result.violations.map(
    (v) => `${v.id}: ${v.nodes.map((n) => n.html).join(" | ")}`,
  );
}

function ok(data: unknown) {
  return {
    data,
    error: undefined,
    response: new Response(null, { status: 200 }),
  };
}

function fail(status: number, code: string, message: string) {
  return {
    data: undefined,
    error: { detail: { code, message } },
    response: new Response(null, { status }),
  };
}

beforeEach(() => post.mockReset());

describe("ResultCard", () => {
  it.each(CARDS.map((c) => [c.kind, c] as const))(
    "renders a %s card",
    (_kind, card) => {
      const { container } = render(<ResultCard card={card} />, { wrapper });
      expect(container.textContent).not.toBe("");
    },
  );

  it("shows the risk result with the band and score from the engine", () => {
    render(<ResultCard card={CARDS[0]} />, { wrapper });
    expect(
      screen.getByRole("img", { name: /score 8 out of 100/i }),
    ).toBeInTheDocument();
  });

  it("explains a locked risk check and links to Import", () => {
    render(
      <ResultCard
        card={{ kind: "risk", title: "Risk check", data: LOCKED_RISK }}
      />,
      {
        wrapper,
      },
    );
    expect(screen.getByText(/unlocks with four months/i)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /import a statement/i }),
    ).toHaveAttribute("href", "/import");
  });

  it("highlights collisions and overdue payments in the bill analysis", () => {
    render(
      <ResultCard card={CARDS.find((c) => c.kind === "bill_analysis")!} />,
      { wrapper },
    );
    expect(screen.getByText(/same week/i).closest("p")).toHaveTextContent(
      "RM 368.51",
    );
    expect(screen.getByText(/overdue/i)).toBeInTheDocument();
    expect(screen.getByText(/unifi went up/i)).toBeInTheDocument();
  });

  it("draws a budget bar with its state for screen readers", () => {
    render(
      <ResultCard card={CARDS.find((c) => c.kind === "budget_status")!} />,
      { wrapper },
    );
    const bar = screen.getByRole("progressbar", { name: "Food budget" });
    expect(bar).toHaveAttribute("aria-valuenow", "100");
    expect(bar).toHaveAttribute("aria-valuetext", "105% used");
    expect(screen.getByText(/over the limit/i)).toBeInTheDocument();
  });

  it("shows how a budget suggestion was worked out", () => {
    render(
      <ResultCard card={CARDS.find((c) => c.kind === "budget_suggestion")!} />,
      { wrapper },
    );
    expect(screen.getByText("How we got this:")).toBeInTheDocument();
    expect(screen.getByText("Left to budget").nextSibling).toHaveTextContent(
      "RM 597.22",
    );
  });

  it("shows each recommendation's source figures", () => {
    render(<ResultCard card={CARDS.find((c) => c.kind === "alerts")!} />, {
      wrapper,
    });
    expect(screen.getByText(/from: spent rm 420.00/i)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Review budgets" }),
    ).toHaveAttribute("href", "/budgets");
  });

  it("flags duplicates and says why a pasted row was left out", () => {
    render(
      <ResultCard card={CARDS.find((c) => c.kind === "paste_preview")!} />,
      { wrapper },
    );
    expect(screen.getByText(/already in your ledger/i)).toBeInTheDocument();
    expect(screen.getByText(/left out: rm 9.99/i)).toBeInTheDocument();
  });

  it("has no detectable accessibility violations across every card", async () => {
    const { container } = render(
      <div>
        {CARDS.map((card, i) => (
          <ResultCard key={i} card={card} />
        ))}
      </div>,
      { wrapper },
    );
    expect(await violations(container)).toEqual([]);
  });
});

describe("StepsList", () => {
  it("lists every tool call with its tier, status and inputs", async () => {
    render(
      <StepsList
        steps={[
          {
            tool: "check_purchase_risk",
            tier: 1,
            status: "ok",
            inputs: { total_price_sen: 79900 },
            summary: "Ran the risk check.",
          },
          {
            tool: "create_plan",
            tier: 2,
            status: "refused",
            inputs: {},
            summary: "That tool changes data.",
          },
        ]}
      />,
    );
    await userEvent.click(screen.getByText("What I did (2 steps)"));
    expect(screen.getByText("Worked out")).toBeInTheDocument();
    expect(screen.getByText("Refused")).toBeInTheDocument();
    expect(screen.getByText("Total price: RM 799.00")).toBeInTheDocument();
  });

  it("renders nothing when no tool ran", () => {
    const { container } = render(<StepsList steps={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ConfirmCard", () => {
  it("is built from the stored proposal and confirms once", async () => {
    post.mockResolvedValue(ok({ id: "a1", type: "set_budget", status: "confirmed", transaction: null, imported: null, plan: null,
      budget: { category: "Food", limit_sen: 40000, updated_at: null }, message: "Food budget saved." })); // prettier-ignore
    render(<ConfirmCard action={BUDGET_ACTION} />, { wrapper });
    expect(
      screen.getByRole("heading", { name: "Save this budget?" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Set the Food budget to RM 400.00 a month."),
    ).toBeInTheDocument();
    expect(screen.getByText("Limit: RM 400.00")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("Food budget saved.")).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith(
      "/api/assistant/actions/{action_id}/confirm",
      {
        params: { path: { action_id: "a1" } },
      },
    );
    expect(
      screen.queryByRole("button", { name: "Confirm" }),
    ).not.toBeInTheDocument();
  });

  it("shows the plan the server worked out and links the saved report", async () => {
    post.mockResolvedValue(ok({ id: "a2", type: "create_plan", status: "confirmed", transaction: null, imported: null, budget: null,
      plan: { check_id: "c-1", check: {}, plan: {} }, message: "Plan added and its risk report saved." })); // prettier-ignore
    render(<ConfirmCard action={PLAN_ACTION} />, { wrapper });
    expect(screen.getAllByText(/RM 799.00/).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(
      await screen.findByRole("link", { name: /saved report/i }),
    ).toHaveAttribute("href", "/risk/c-1");
  });

  it("says an expired proposal must be asked for again", async () => {
    post.mockResolvedValue(
      fail(410, "action_expired", "This proposal has expired. Ask again."),
    );
    render(<ConfirmCard action={BUDGET_ACTION} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(
      await screen.findByText(/expired\. ask again to get a fresh one/i),
    ).toBeInTheDocument();
  });

  it("says a used proposal cannot be used twice", async () => {
    post.mockResolvedValue(
      fail(409, "action_not_pending", "Already confirmed."),
    );
    render(<ConfirmCard action={BUDGET_ACTION} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText(/already been used/i)).toBeInTheDocument();
  });

  it("cancels without changing anything", async () => {
    post.mockResolvedValue(ok({ id: "a1", type: "set_budget", status: "declined", transaction: null, imported: null, plan: null,
      budget: null, message: "Nothing was changed." })); // prettier-ignore
    render(<ConfirmCard action={BUDGET_ACTION} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(screen.getByText("Cancelled")).toBeInTheDocument(),
    );
    expect(post.mock.calls[0][0]).toBe(
      "/api/assistant/actions/{action_id}/decline",
    );
  });

  it("lists the rows of an import proposal", () => {
    render(
      <ConfirmCard
        action={{
          id: "a3",
          type: "confirm_import",
          status: "pending",
          summary: "Add 1 transaction(s).",
          expires_at: "x",
          payload: {
            rows: [
              {
                date: "2025-12-27",
                amount_sen: 1500,
                type: "expense",
                category: "Transport",
                description: "Grab",
              },
            ],
          },
        }}
      />,
      { wrapper },
    );
    expect(screen.getByText(/27 December 2025 · Grab/)).toBeInTheDocument();
    expect(screen.getByText("-RM 15.00")).toBeInTheDocument();
  });
});

describe("AssistantMessage", () => {
  it("shows the reply without markdown, the steps, cards and proposals", () => {
    render(
      <AssistantMessage
        reply={reply({
          reply: "This is **At Risk**.",
          narration_replaced: true,
          cards: [CARDS[1]],
          pending_actions: [BUDGET_ACTION],
          steps: [
            {
              tool: "get_forecast",
              tier: 0,
              status: "ok",
              inputs: {},
              summary: "Ran the forecast.",
            },
          ],
        })}
      />,
      { wrapper },
    );
    expect(screen.getByText("This is At Risk.")).toBeInTheDocument();
    expect(
      screen.getByText(/plain summary is shown instead/i),
    ).toBeInTheDocument();
    const card = screen.getByRole("region", { name: "Save this budget?" });
    expect(within(card).getByRole("button", { name: "Confirm" })).toBeEnabled();
  });
});

describe("ResultCard: the Second-Opinion Check (D-57)", () => {
  it("shows what the purchase adds inside the assistant's risk card", () => {
    render(<ResultCard card={CARDS[0]} />, { wrapper });
    expect(
      screen.getByRole("region", { name: /what this purchase adds/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: /what you owe each month/i }),
    ).toBeInTheDocument();
  });

  it("shows the timing search read-only, with nothing to press", async () => {
    const card = CARDS.find((c) => c.kind === "schedule")!;
    const { container } = render(<ResultCard card={card} />, { wrapper });
    expect(
      screen.getByRole("list", { name: /options tried/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(await violations(container)).toEqual([]);
  });
});
