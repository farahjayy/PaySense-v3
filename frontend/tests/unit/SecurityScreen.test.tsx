import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SecurityScreen } from "@/components/screens/SecurityScreen";
import type { Drill } from "@/lib/api/queries";

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

const CLASSES = [
  "induced_transfers",
  "data_extraction",
  "privilege_escalation",
  "prompt_injection",
] as const;

function attack(
  id: string,
  attackClass: (typeof CLASSES)[number],
  harmed = false,
) {
  return {
    id,
    attack_class: attackClass,
    title: `Attack ${id}`,
    tried: `The model tried ${id}`,
    stopped_by: `Control for ${id}`,
    fooled: true,
    harmed,
    evidence: `Evidence for ${id}`,
  };
}

function drill(harmedId?: string): Drill {
  const attacks = CLASSES.flatMap((c) =>
    [1, 2, 3].map((n) => attack(`${c}_${n}`, c, `${c}_${n}` === harmedId)),
  );
  return {
    attacks,
    totals: CLASSES.map((c) => ({
      attack_class: c,
      attacks: 3,
      fooled: 3,
      harmed: attacks.filter((a) => a.attack_class === c && a.harmed).length,
    })),
    duration_ms: 812,
    sandbox: true,
    model: "scripted_hostile",
  };
}

function ok(data: unknown) {
  return { data, error: undefined, response: { ok: true, status: 200 } };
}

describe("SecurityScreen", () => {
  beforeEach(() => post.mockReset());

  it("explains the drill before it runs and runs nothing on its own", () => {
    render(<SecurityScreen />, { wrapper });
    expect(
      screen.getByRole("heading", { level: 1, name: /security drill/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/throwaway sandbox/i)).toBeInTheDocument();
    expect(screen.getByText(/obeys every instruction/i)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("runs the drill and shows the scoreboard for the four named classes", async () => {
    post.mockResolvedValue(ok(drill()));
    const user = userEvent.setup();
    render(<SecurityScreen />, { wrapper });
    await user.click(screen.getByRole("button", { name: /run the drill/i }));

    expect(post.mock.calls[0][0]).toBe("/api/security/drill");
    const board = await screen.findByRole("table", { name: /scoreboard/i });
    const rows = within(board).getAllByRole("row");
    expect(rows).toHaveLength(6); // header, four classes, total
    expect(within(rows[1]).getByText("Induced transfers")).toBeInTheDocument();
    expect(within(rows[5]).getAllByText("12")).toHaveLength(2); // attacks and model fooled
    expect(
      screen.getByText(/12 of 12 attacks fooled the model/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no harm done in any of them/i),
    ).toBeInTheDocument();
  });

  it("lists every attack with what was tried, what stopped it and the evidence", async () => {
    post.mockResolvedValue(ok(drill()));
    const user = userEvent.setup();
    render(<SecurityScreen />, { wrapper });
    await user.click(screen.getByRole("button", { name: /run the drill/i }));

    const group = await screen.findByRole("region", {
      name: "Prompt injection",
    });
    expect(within(group).getAllByRole("listitem")).toHaveLength(3);
    await user.click(within(group).getByText("Attack prompt_injection_1"));
    expect(
      within(group).getByText("The model tried prompt_injection_1"),
    ).toBeVisible();
    expect(
      within(group).getByText("Control for prompt_injection_1"),
    ).toBeVisible();
    expect(
      within(group).getByText("Evidence for prompt_injection_1"),
    ).toBeVisible();
  });

  it("says plainly when an attack did harm, instead of hiding it", async () => {
    post.mockResolvedValue(ok(drill("data_extraction_2")));
    const user = userEvent.setup();
    render(<SecurityScreen />, { wrapper });
    await user.click(screen.getByRole("button", { name: /run the drill/i }));

    expect(await screen.findByText(/1 attack did harm/i)).toBeInTheDocument();
    const group = screen.getByRole("region", { name: "Data extraction" });
    expect(within(group).getByText(/harm done/i)).toBeInTheDocument();
  });

  it("has no detectable accessibility violations with a result on screen", async () => {
    post.mockResolvedValue(ok(drill()));
    const user = userEvent.setup();
    const { container } = render(<SecurityScreen />, { wrapper });
    await user.click(screen.getByRole("button", { name: /run the drill/i }));
    await screen.findByRole("table", { name: /scoreboard/i });
    const result = await axe.run(container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(result.violations.map((v) => v.id)).toEqual([]);
  });
});
