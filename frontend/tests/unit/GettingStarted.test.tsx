import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GettingStarted } from "@/components/dashboard/GettingStarted";

const get = vi.fn();
vi.mock("@/lib/api/client", () => ({ api: { GET: (...a: unknown[]) => get(...a) } }));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

/** Renders with a client the test can ask "has everything finished loading?". */
function renderSettled() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <GettingStarted />
    </QueryClientProvider>,
  );
  const settled = () =>
    vi.waitFor(() => {
      expect(get).toHaveBeenCalled();
      expect(client.isFetching()).toBe(0);
    });
  return { ...view, settled };
}

type World = {
  months?: number;
  status?: "ok" | "locked";
  recurring?: unknown[];
  limits?: { provider: string; limit_sen: number | null }[];
  plans?: { id: string; risk_score_at_creation: number | null }[];
};

function serve(world: World = {}) {
  const data: Record<string, unknown> = {
    "/api/forecast": { status: world.status ?? "locked", months_of_history: world.months ?? 0 },
    "/api/summary/months": { months: [], history: null },
    "/api/recurring-items": world.recurring ?? [],
    "/api/provider-limits": world.limits ?? [
      { provider: "spaylater", limit_sen: null },
      { provider: "atome", limit_sen: null },
    ],
    "/api/plans": world.plans ?? [],
  };
  get.mockImplementation(async (path: string) => {
    if (!(path in data)) throw new Error(`unexpected GET ${path}`);
    return { data: data[path], error: undefined, response: { ok: true, status: 200 } };
  });
}

describe("GettingStarted", () => {
  beforeEach(() => {
    get.mockReset();
    window.localStorage.clear();
  });

  it("walks a new student through the five steps, each with why it matters", async () => {
    serve({ months: 2 });
    render(<GettingStarted />, { wrapper });

    const list = await screen.findByRole("list", { name: /getting started steps/i });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(5);
    expect(items[0]).toHaveTextContent("Bring in your spending");
    expect(items[0]).toHaveTextContent("2 of 4 months so far");
    expect(items[1]).toHaveTextContent("Rent, allowance, PTPTN and subscriptions");
    expect(screen.getByText("0 of 5 done")).toBeInTheDocument();
  });

  it("marks what is already done and links each step still to do to its page", async () => {
    serve({
      months: 5,
      status: "ok",
      recurring: [{ id: "r1" }],
      limits: [{ provider: "spaylater", limit_sen: 200000 }],
    });
    render(<GettingStarted />, { wrapper });

    const list = await screen.findByRole("list", { name: /getting started steps/i });
    const items = within(list).getAllByRole("listitem");
    for (const finished of items.slice(0, 4)) {
      expect(within(finished).getByText("Done")).toBeInTheDocument();
    }
    expect(within(items[4]).getByText("To do")).toBeInTheDocument();
    expect(within(items[4]).getByRole("link", { name: /risk check/i })).toHaveAttribute(
      "href",
      "/risk",
    );
    expect(within(items[0]).queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("4 of 5 done")).toBeInTheDocument();
  });

  it("gets out of the way once every step is done, the risk check counted from a plan made from one", async () => {
    serve({
      months: 5,
      status: "ok",
      recurring: [{ id: "r1" }],
      limits: [{ provider: "atome", limit_sen: 50000 }],
      plans: [{ id: "p1", risk_score_at_creation: 61 }],
    });
    const { container, settled } = renderSettled();

    await settled(); // the data really has arrived, so an empty card is a decision, not a delay
    expect(container).toBeEmptyDOMElement();
  });

  it("is still there when the same student has not made a risk check, so the empty case above is real", async () => {
    serve({
      months: 5,
      status: "ok",
      recurring: [{ id: "r1" }],
      limits: [{ provider: "atome", limit_sen: 50000 }],
      plans: [{ id: "p1", risk_score_at_creation: null }],
    });
    const { settled } = renderSettled();

    await settled();
    expect(await screen.findByText("4 of 5 done")).toBeInTheDocument();
  });

  it("can be hidden by a student who will never do every step, and stays hidden next visit", async () => {
    serve({ months: 5, status: "ok" });
    const first = render(<GettingStarted />, { wrapper });
    await screen.findByRole("list", { name: /getting started steps/i });

    await userEvent.click(screen.getByRole("button", { name: /hide this/i }));

    expect(screen.queryByRole("list", { name: /getting started steps/i })).not.toBeInTheDocument();
    first.unmount();
    const { settled, container } = renderSettled();
    await settled();
    expect(container).toBeEmptyDOMElement();
  });

  it("shows nothing until it knows, so a finished student never sees it flash up", () => {
    get.mockImplementation(() => new Promise(() => {}));
    const { container } = render(<GettingStarted />, { wrapper });

    expect(container).toBeEmptyDOMElement();
  });

  it("stays out of the way when it cannot tell, rather than show a wrong checklist", async () => {
    get.mockImplementation(async (path: string) =>
      path === "/api/plans"
        ? {
            data: undefined,
            error: { detail: { code: "x", message: "down" } },
            response: { ok: false, status: 500 },
          }
        : { data: [], error: undefined, response: { ok: true, status: 200 } },
    );
    const { container, settled } = renderSettled();

    await settled();
    expect(container).toBeEmptyDOMElement();
  });
});
