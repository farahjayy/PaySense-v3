import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AssistantPanel } from "@/components/assistant/AssistantPanel";
import { AppShell } from "@/components/layout/AppShell";
import type { AssistantStatus } from "@/lib/assistant";
import { useOpenAssistant } from "@/lib/assistantLauncher";

import { BUDGET_ACTION, CARDS, reply } from "./assistantFixtures";

const get = vi.fn();
const post = vi.fn();
vi.mock("@/lib/api/client", () => ({
  api: {
    GET: (...a: unknown[]) => get(...a),
    POST: (...a: unknown[]) => post(...a),
  },
}));
vi.mock("next/dynamic", () => ({ default: () => () => <div aria-hidden /> }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/",
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const ok = (data: unknown) => ({
  data,
  error: undefined,
  response: new Response(null, { status: 200 }),
});
const fail = (status: number, code: string, message: string) => ({
  data: undefined,
  error: { detail: { code, message } },
  response: new Response(null, { status }),
});

const LLM_STATUS: AssistantStatus = {
  mode: "llm",
  provider: "gemini",
  model: "m",
  reason: null,
  tokens_used_today: 0,
  daily_token_budget: 1,
};
const GUIDED_STATUS: AssistantStatus = {
  ...LLM_STATUS,
  mode: "guided",
  provider: null,
  model: null,
  reason: "No API key is set for gemini.",
};
const OPENING = reply({
  mode: "guided",
  reply: "Here is what needs your attention: Food is over budget.",
  cards: [CARDS.find((c) => c.kind === "alerts")!],
});

function routes(status: AssistantStatus = LLM_STATUS) {
  get.mockImplementation(async (path: string) => {
    if (path === "/api/assistant/status") return ok(status);
    if (path === "/api/assistant/opening") return ok(OPENING);
    if (path === "/api/providers")
      return ok([
        {
          key: "spaylater",
          label: "SPayLater",
          rule_driven: true,
          checkout_instalments: 0,
          start_rule: "months_after_purchase",
          start_offset_months: 1,
          monthly_fee_applies: true,
        },
      ]);
    throw new Error(`unexpected GET ${path}`);
  });
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

describe("AssistantPanel", () => {
  it("opens with the alerts, focuses the message box and says it is not advice", async () => {
    routes();
    render(<AssistantPanel onClose={vi.fn()} />, { wrapper });
    expect(await screen.findByText(/food is over budget\./i)).toBeInTheDocument();
    expect(screen.getByLabelText("Your message")).toHaveFocus();
    expect(screen.getByText(/not financial advice or a credit decision/i)).toBeInTheDocument();
    expect(await screen.findByText("Assistant on (gemini)")).toBeInTheDocument();
  });

  it("sends a message with plain-text history and shows the reply, steps and cards", async () => {
    routes();
    post.mockResolvedValueOnce(ok(reply({
      reply: "It is At Risk with a score of 8.",
      steps: [{ tool: "check_purchase_risk", tier: 1, status: "ok", inputs: {}, summary: "Ran the risk check." }],
      cards: [CARDS[0]],
    }))); // prettier-ignore
    render(<AssistantPanel onClose={vi.fn()} />, { wrapper });
    await screen.findByText(/food is over budget\./i);
    await userEvent.type(
      screen.getByLabelText("Your message"),
      "Can I afford an RM799 phone?{Enter}",
    );
    expect(await screen.findByText("It is At Risk with a score of 8.")).toBeInTheDocument();
    const [path, { body }] = post.mock.calls[0];
    expect(path).toBe("/api/assistant/chat");
    expect(body.message).toBe("Can I afford an RM799 phone?");
    expect(body.history).toEqual([{ role: "assistant", text: OPENING.reply }]);
    expect(body).not.toHaveProperty("pasted_text");
    expect(screen.getByText("What I did (1 step)")).toBeInTheDocument();
  });

  it("offers the demo prompts as one-tap questions", async () => {
    routes();
    post.mockResolvedValueOnce(ok(reply({ reply: "Done." })));
    render(<AssistantPanel onClose={vi.fn()} />, { wrapper });
    await userEvent.click(await screen.findByRole("button", { name: /RM799 phone on SPayLater/ }));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][1].body.message).toMatch(/RM799 phone/);
  });

  it("sends a paste as labelled data", async () => {
    routes();
    post.mockResolvedValueOnce(ok(reply({ pending_actions: [BUDGET_ACTION] })));
    render(<AssistantPanel onClose={vi.fn()} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: "Paste" }));
    await userEvent.type(screen.getByLabelText(/pasted transactions/i), "27/12 Grab 15.00");
    await userEvent.type(screen.getByLabelText("Your message"), "Add these{Enter}");
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][1].body.pasted_text).toBe("27/12 Grab 15.00");
    expect(await screen.findByRole("heading", { name: "Save this budget?" })).toBeInTheDocument();
  });

  it("in guided mode runs quick actions and forms through the same tools", async () => {
    routes(GUIDED_STATUS);
    post.mockResolvedValue(
      ok(
        reply({
          mode: "guided",
          reply: "Checked 1 budget(s).",
          cards: [CARDS.find((c) => c.kind === "budget_status")!],
        }),
      ),
    );
    render(<AssistantPanel onClose={vi.fn()} />, { wrapper });
    expect(await screen.findByText("No API key is set for gemini.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "My budgets" }));
    expect(await screen.findByText("Checked 1 budget(s).")).toBeInTheDocument();
    expect(post.mock.calls[0]).toEqual([
      "/api/assistant/run",
      { body: { tool: "get_budget_status", arguments: {} } },
    ]);

    await userEvent.click(screen.getByRole("button", { name: "Set a budget" }));
    await userEvent.type(screen.getByLabelText("Category"), "Food");
    await userEvent.type(screen.getByLabelText("Monthly limit (RM)"), "400");
    await userEvent.click(screen.getByRole("button", { name: "Propose this budget" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[1][1].body).toEqual({
      tool: "propose_action",
      arguments: {
        type: "set_budget",
        payload: { category: "Food", limit_sen: 40000 },
      },
    });
  });

  it("checks a purchase from the guided form", async () => {
    routes(GUIDED_STATUS);
    post.mockResolvedValue(ok(reply({ mode: "guided", reply: "Ran the risk check." })));
    render(<AssistantPanel onClose={vi.fn()} />, { wrapper });
    await userEvent.click(await screen.findByRole("button", { name: "Check a purchase" }));
    await userEvent.type(screen.getByLabelText("What are you buying?"), "Phone");
    await userEvent.type(screen.getByLabelText("Price (RM)"), "799");
    await userEvent.click(screen.getByRole("button", { name: "Check it" }));
    await waitFor(() => expect(post).toHaveBeenCalled());
    const body = post.mock.calls[0][1].body;
    expect(body.tool).toBe("check_purchase_risk");
    expect(body.arguments).toMatchObject({
      item_name: "Phone",
      total_price_sen: 79900,
      num_installments: 3,
    });
  });

  it("adds a transaction and pastes a statement from the guided forms", async () => {
    routes(GUIDED_STATUS);
    post.mockResolvedValue(ok(reply({ mode: "guided", reply: "Proposed." })));
    render(<AssistantPanel onClose={vi.fn()} />, { wrapper });
    await userEvent.click(await screen.findByRole("button", { name: "Add a transaction" }));
    await userEvent.type(screen.getByLabelText("Amount (RM)"), "12.50");
    await userEvent.type(screen.getByLabelText("Category"), "Food");
    await userEvent.click(screen.getByRole("button", { name: "Propose this transaction" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][1].body.arguments.payload.amount_sen).toBe(1250);
    await userEvent.click(screen.getByRole("button", { name: "Paste transactions" }));
    await userEvent.type(
      screen.getByLabelText(/date, description and amount/i),
      "Date,Description,Amount",
    );
    await userEvent.click(screen.getByRole("button", { name: "Read it" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[1][1].body).toMatchObject({
      tool: "parse_pasted_transactions",
      pasted_text: "Date,Description,Amount",
    });
  });

  it.each([
    [403, "consent_required", "Accept the privacy notice first"],
    [429, "assistant_daily_budget", "Today's assistant allowance is used"],
    [429, "too_many_requests", "Slow down a little"],
    [500, "internal_error", "That did not work"],
  ])("explains a %s %s and keeps guided actions where they help", async (status, code, title) => {
    routes();
    post.mockResolvedValueOnce(fail(status, code, "The server said no."));
    render(<AssistantPanel onClose={vi.fn()} />, { wrapper });
    await userEvent.type(screen.getByLabelText("Your message"), "hi{Enter}");
    expect(await screen.findByText(title)).toBeInTheDocument();
    if (code === "consent_required") {
      expect(screen.getByRole("link", { name: /privacy notice/i })).toHaveAttribute(
        "href",
        "/account",
      );
    }
    const guided = code === "consent_required" || code === "assistant_daily_budget";
    const quick = screen.getByRole("group", { name: "Quick actions" });
    expect(quick.closest("details")!.open).toBe(guided);
  });

  it("keeps the quick actions one tap away in llm mode, behind a closed disclosure", async () => {
    routes();
    post.mockResolvedValueOnce(ok(reply({ reply: "Your forecast." })));
    render(<AssistantPanel onClose={vi.fn()} />, { wrapper });
    const summary = await screen.findByText("Quick actions and forms (no model)");
    const details = summary.closest("details")!;
    expect(details.open).toBe(false);
    await userEvent.click(summary);
    expect(details.open).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "My forecast" }));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][0]).toBe("/api/assistant/run");
    expect(post.mock.calls[0][1].body).toMatchObject({ tool: "get_forecast" });
  });

  it("says when the server cannot be reached", async () => {
    routes();
    post.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    render(<AssistantPanel onClose={vi.fn()} />, { wrapper });
    await userEvent.type(screen.getByLabelText("Your message"), "hi{Enter}");
    expect(await screen.findByText("You seem to be offline")).toBeInTheDocument();
  });

  it("closes with Escape and with the Close button", async () => {
    routes();
    const onClose = vi.fn();
    render(<AssistantPanel onClose={onClose} />, { wrapper });
    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("closes when a link takes the user to another screen", async () => {
    routes();
    const onClose = vi.fn();
    render(<AssistantPanel onClose={onClose} />, { wrapper });
    const link = await screen.findByRole("link", { name: "Review budgets" });
    link.addEventListener("click", (e) => e.preventDefault()); // jsdom cannot navigate
    await userEvent.click(link);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("has no detectable accessibility violations, in llm and guided mode", async () => {
    routes();
    const first = render(<AssistantPanel onClose={vi.fn()} />, { wrapper });
    await screen.findByText(/food is over budget\./i);
    let result = await axe.run(first.container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(result.violations.map((v) => v.id)).toEqual([]);
    first.unmount();
    routes(GUIDED_STATUS);
    const second = render(<AssistantPanel onClose={vi.fn()} />, { wrapper });
    await screen.findByText("No API key is set for gemini.");
    result = await axe.run(second.container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(result.violations.map((v) => v.id)).toEqual([]);
  });
});

function phoneWidth(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: (query: string) => ({
      matches,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }),
  });
}

describe("the panel on a phone and on a desktop", () => {
  it("is a modal dialog on a phone and keeps the keyboard inside it", async () => {
    routes();
    phoneWidth(true);
    render(<AssistantPanel onClose={vi.fn()} />, { wrapper });
    const dialog = screen.getByRole("dialog", { name: "Ask PaySense" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const close = screen.getByRole("button", { name: "Close" });
    close.focus();
    await userEvent.tab({ shift: true }); // backwards from the first control
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(document.activeElement).not.toBe(close);
    await userEvent.tab(); // and forwards from the last one, back to the first
    expect(document.activeElement).toBe(close);
  });

  it("is a side panel beside the page on a desktop", () => {
    routes();
    phoneWidth(false);
    render(<AssistantPanel onClose={vi.fn()} />, { wrapper });
    expect(screen.getByRole("dialog", { name: "Ask PaySense" })).toHaveAttribute(
      "aria-modal",
      "false",
    );
  });
});

describe("what a quick action says in the conversation", () => {
  it("shows the button's own words, not the tool's name", async () => {
    routes(GUIDED_STATUS);
    post.mockResolvedValue(ok(reply({ mode: "guided", reply: "Checked 1 budget(s).", cards: [] })));
    render(<AssistantPanel onClose={vi.fn()} />, { wrapper });
    await userEvent.click(await screen.findByRole("button", { name: "My budgets" }));
    const log = screen.getByRole("log", { name: "Conversation" });
    expect(log).toHaveTextContent("You: My budgets");
    expect(log).not.toHaveTextContent("Get budget status");
  });
});

describe("opening the assistant from a page", () => {
  it("puts the page's prompt in the message box without sending it", async () => {
    routes();
    const user = { id: "u1", username: "amir", display_name: "Amir", persona: null } as const;
    function Page() {
      const open = useOpenAssistant();
      return (
        <button type="button" onClick={() => open?.("What's the safest way to buy it?")}>
          try it
        </button>
      );
    }
    render(
      <AppShell user={user}>
        <Page />
      </AppShell>,
      { wrapper },
    );
    await userEvent.click(screen.getByRole("button", { name: "try it" }));
    expect(screen.getByRole("dialog", { name: "Ask PaySense" })).toBeInTheDocument();
    expect(screen.getByLabelText("Your message")).toHaveValue("What's the safest way to buy it?");
    expect(post).not.toHaveBeenCalled();
  });
});

describe("the Ask PaySense button", () => {
  it("opens the panel from any page and returns focus when it closes", async () => {
    routes();
    const user = {
      id: "u1",
      username: "amir",
      display_name: "Amir",
      persona: null,
    } as const;
    render(
      <AppShell user={user}>
        <p>page</p>
      </AppShell>,
      { wrapper },
    );
    const ask = screen.getByRole("button", { name: "Ask PaySense" });
    await userEvent.click(ask);
    expect(screen.getByRole("dialog", { name: "Ask PaySense" })).toBeInTheDocument();
    expect(ask).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(ask).toHaveFocus();
  });
});
