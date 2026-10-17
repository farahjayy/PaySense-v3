import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BudgetStrip } from "@/components/dashboard/BudgetStrip";
import { TryThis } from "@/components/dashboard/TryThis";
import { SUGGESTED_PROMPTS } from "@/lib/assistant";
import { AssistantLauncher } from "@/lib/assistantLauncher";

import { BUDGET_STATUS, ok, wrapper } from "./topicTestUtils";

const get = vi.fn();
vi.mock("@/lib/api/client", () => ({ api: { GET: (...a: unknown[]) => get(...a) } }));

describe("TryThis", () => {
  it("leads a first-time visitor through afford, safest option and confirm", async () => {
    const open = vi.fn();
    render(
      <AssistantLauncher.Provider value={open}>
        <TryThis />
      </AssistantLauncher.Provider>,
    );
    expect(screen.getByRole("heading", { name: "Try this" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: new RegExp(SUGGESTED_PROMPTS[0]) }));
    expect(open).toHaveBeenCalledWith(SUGGESTED_PROMPTS[0]);
    await userEvent.click(screen.getByRole("button", { name: new RegExp(SUGGESTED_PROMPTS[1]) }));
    expect(open).toHaveBeenLastCalledWith(SUGGESTED_PROMPTS[1]);
    expect(screen.getByText(/nothing changes until you press confirm/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /your data/i })).toHaveAttribute("href", "/account");
  });

  it("is not shown where there is no assistant to open", () => {
    const { container } = render(<TryThis />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("BudgetStrip", () => {
  beforeEach(() => get.mockReset());

  it("shows each budget's spending and state in words, linking to the budgets page", async () => {
    get.mockResolvedValue(ok(BUDGET_STATUS));
    render(<BudgetStrip />, { wrapper });
    expect(await screen.findByText("Food")).toBeInTheDocument();
    expect(screen.getByText(/RM 80\.00 of RM 100\.00/)).toBeInTheDocument();
    expect(screen.getByText(/close to the limit/i)).toBeInTheDocument();
    expect(screen.getByText(/over the limit/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /all budgets/i })).toHaveAttribute("href", "/budgets");
  });

  it("invites setting a first budget when there are none", async () => {
    get.mockResolvedValue(ok({ ...BUDGET_STATUS, items: [], total_limit_sen: 0 }));
    render(<BudgetStrip />, { wrapper });
    expect(await screen.findByRole("link", { name: /set a budget/i })).toHaveAttribute(
      "href",
      "/budgets",
    );
  });
});
