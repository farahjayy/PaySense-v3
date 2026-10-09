import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ModelScreen } from "@/components/screens/ModelScreen";

const get = vi.fn();
vi.mock("@/lib/api/client", () => ({ api: { GET: (...a: unknown[]) => get(...a) } }));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const INFO = {
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
};

function serve(data: unknown, ok = true) {
  get.mockResolvedValue(
    ok
      ? { data, error: undefined, response: { ok: true, status: 200 } }
      : {
          data: undefined,
          error: { detail: { code: "x", message: "down" } },
          response: { ok: false, status: 500 },
        },
  );
}

describe("ModelScreen", () => {
  beforeEach(() => {
    get.mockReset();
    serve(INFO);
  });

  it("never shows internal engine names to the user", async () => {
    const { container } = render(<ModelScreen />, { wrapper });
    await screen.findByText(/gradient-boosted trees/i);
    expect(container.textContent).not.toMatch(/engine\s*[12]/i);
  });

  it("states the band cut-offs and the known weaknesses", () => {
    render(<ModelScreen />, { wrapper });
    expect(screen.getByText(/under a 10% chance/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /where it is weak/i })).toBeInTheDocument();
    expect(screen.getByText(/savings you hold are not counted/i)).toBeInTheDocument();
    expect(screen.getByText(/not financial advice/i)).toBeInTheDocument();
  });

  it("has one h1 and every section is a labelled region", async () => {
    render(<ModelScreen />, { wrapper });
    await screen.findByRole("region", { name: /what is running now/i });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    for (const name of [
      /financial health forecast/i,
      /bnpl risk check/i,
      /what it was built from/i,
    ]) {
      expect(screen.getByRole("region", { name })).toBeInTheDocument();
    }
  });

  it("shows what is serving now, read from the server, with its accuracy against guessing", async () => {
    render(<ModelScreen />, { wrapper });

    expect(await screen.findByText(/gradient-boosted trees, version v1/i)).toBeInTheDocument();
    expect(screen.getByText(/9,000 simulated students/i)).toBeInTheDocument();
    expect(screen.getByText(/0\.0198, against 0\.1788/i)).toBeInTheDocument();
    expect(screen.getByText(/recurrent neural network, version v1/i)).toBeInTheDocument();
  });

  it("says when the risk model is not on this server, and survives the details failing to load", async () => {
    serve({ ...INFO, risk: { ...INFO.risk, available: false, version: null, family: null } });
    const { unmount } = render(<ModelScreen />, { wrapper });
    expect(await screen.findByText(/not available on this server/i)).toBeInTheDocument();
    unmount();

    serve(null, false);
    render(<ModelScreen />, { wrapper });
    expect(screen.getByRole("heading", { level: 1, name: /about the model/i })).toBeInTheDocument();
    await screen.findByRole("heading", { name: /where it is weak/i });
  });
});
