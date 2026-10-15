import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/AppShell";
import { AuthGate } from "@/components/auth/AuthGate";
import { clearSession, getSession, saveSession } from "@/lib/session";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/",
}));

const get = vi.fn();
vi.mock("@/lib/api/client", () => ({ api: { GET: (...args: unknown[]) => get(...args) } }));

const USER = { id: "u1", username: "amir", display_name: "Amir", persona: null } as const;

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function signIn() {
  saveSession({ token: "t", expiresAt: Date.now() + 60_000, user: USER });
}

describe("AuthGate", () => {
  beforeEach(() => {
    replace.mockReset();
    get.mockReset();
    get.mockResolvedValue({ data: USER, error: undefined });
  });

  it("sends visitors without a session to the login page and shows nothing private", async () => {
    render(<AuthGate>secret content</AuthGate>, { wrapper });

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });

  it("renders its children for a signed-in user and does not redirect", async () => {
    signIn();
    render(<AuthGate>private content</AuthGate>, { wrapper });

    expect(await screen.findByText("private content")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("checks the session with the server and bounces the user if it was revoked", async () => {
    signIn();
    get.mockImplementation(async () => {
      clearSession(); // what the API client does on a 401
      return { data: undefined, error: { detail: { code: "invalid_token", message: "expired" } } };
    });
    render(<AuthGate>private content</AuthGate>, { wrapper });

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(get).toHaveBeenCalledWith("/api/auth/me");
  });
});

describe("AppShell", () => {
  beforeEach(() => {
    replace.mockReset();
    signIn();
  });

  it("greets the signed-in user and marks the current page", () => {
    render(
      <AppShell user={USER}>
        <p>page body</p>
      </AppShell>,
      { wrapper },
    );

    expect(screen.getAllByText("Amir").length).toBeGreaterThan(0);
    expect(screen.getByText("page body")).toBeInTheDocument();
    const dashboardLinks = screen.getAllByRole("link", { name: /dashboard/i });
    expect(dashboardLinks.some((l) => l.getAttribute("aria-current") === "page")).toBe(true);
  });

  it("links every screen from the sidebar and keeps five on the phone bar", () => {
    render(
      <AppShell user={USER}>
        <p>page body</p>
      </AppShell>,
      { wrapper },
    );

    for (const name of [
      "Dashboard",
      "Transactions",
      "Categories",
      "Recurring",
      "Plans",
      "Risk check",
      "Import",
      "About the model",
    ]) {
      expect(screen.getAllByRole("link", { name: new RegExp(name, "i") }).length).toBeGreaterThan(
        0,
      );
    }
    const phoneBar = screen.getAllByRole("navigation").find((n) => n.className.includes("fixed"));
    expect(phoneBar && phoneBar.querySelectorAll("a").length).toBe(5);
  });

  it("keeps Recurring and About the model reachable on a phone in a 'More pages' row", () => {
    render(
      <AppShell user={USER}>
        <p>page body</p>
      </AppShell>,
      { wrapper },
    );

    const more = screen.getByRole("navigation", { name: "More pages" });
    expect(within(more).getByRole("link", { name: "Recurring" })).toHaveAttribute(
      "href",
      "/recurring",
    );
    expect(within(more).getByRole("link", { name: "About the model" })).toHaveAttribute(
      "href",
      "/model",
    );
    expect(within(more).getByRole("link", { name: "Categories" })).toHaveAttribute(
      "href",
      "/categories",
    );
  });

  it("offers a skip link that targets the focusable main region", () => {
    render(
      <AppShell user={USER}>
        <p>page body</p>
      </AppShell>,
      { wrapper },
    );

    const skip = screen.getByRole("link", { name: /skip to content/i });
    expect(skip).toHaveAttribute("href", "#main");
    const main = screen.getByRole("main");
    expect(main).toHaveAttribute("id", "main");
    expect(main).toHaveAttribute("tabindex", "-1");
  });

  it("logs out: forgets the session and returns to the login page", async () => {
    render(
      <AppShell user={USER}>
        <p>page body</p>
      </AppShell>,
      { wrapper },
    );

    await userEvent.click(screen.getByRole("button", { name: /log out/i }));

    expect(getSession()).toBeNull();
    expect(replace).toHaveBeenCalledWith("/login");
  });
});
