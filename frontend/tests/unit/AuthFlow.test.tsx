import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, act } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthGate } from "@/components/auth/AuthGate";
import { clearSession, getSession, saveSession } from "@/lib/session";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }), usePathname: () => "/" }));

// The REAL client and middleware, talking to a scripted network.
const network = vi.fn<(request: Request) => Promise<Response>>();
vi.mock("@/lib/api/client", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/api/client")>();
  return { ...real, api: real.createApiClient("http://api.test", (request) => network(request)) };
});

const USER = { id: "u1", username: "amir", display_name: "Amir", persona: null };

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function setup(queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

describe("a real 401 travelling through client, middleware and AuthGate", () => {
  beforeEach(() => {
    replace.mockReset();
    network.mockReset();
  });

  it("clears the session and sends the visitor to /welcome", async () => {
    saveSession({ token: "stale", expiresAt: Date.now() + 60_000, user: USER });
    network.mockResolvedValue(json(401, { detail: { code: "invalid_token", message: "expired" } }));
    const { wrapper } = setup();

    render(<AuthGate>private</AuthGate>, { wrapper });

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/welcome"));
    expect(getSession()).toBeNull();
    expect(network.mock.calls[0][0].headers.get("authorization")).toBe("Bearer stale");
  });

  it("forgets cached data when the session ends, so the next user never sees it", async () => {
    saveSession({ token: "t", expiresAt: Date.now() + 60_000, user: USER });
    network.mockResolvedValue(json(200, USER));
    const { queryClient, wrapper } = setup();
    queryClient.setQueryData(["transactions"], [{ id: "private-row" }]);
    render(<AuthGate>private</AuthGate>, { wrapper });
    await screen.findByText("private");

    act(() => clearSession());

    await waitFor(() => expect(queryClient.getQueryData(["transactions"])).toBeUndefined());
  });
});
