import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/AppShell";
import { AuthGate } from "@/components/auth/AuthGate";
import { tourSeen } from "@/lib/introTour";
import { clearSession, getSession, saveSession } from "@/lib/session";

const replace = vi.fn();
const prefetch = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, prefetch }),
  usePathname: () => "/",
}));

const get = vi.fn();
const post = vi.fn(async () => ({ data: undefined, error: undefined }));
vi.mock("@/lib/api/client", () => ({
  api: {
    GET: (...args: unknown[]) => get(...args),
    POST: (...args: unknown[]) => post(...(args as [])),
  },
}));

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

  it("sends visitors without a session to the welcome page and shows nothing private", async () => {
    render(<AuthGate>secret content</AuthGate>, { wrapper });

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/welcome"));
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

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/welcome"));
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

  it("links every screen from the sidebar and keeps four plus More on the phone bar", () => {
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
    const phoneBar = screen.getByRole("navigation", { name: "Quick navigation" });
    expect(phoneBar.querySelectorAll("a")).toHaveLength(4);
    expect(within(phoneBar).getByRole("button", { name: /more/i })).toBeInTheDocument();
  });

  it("groups the sidebar into sections", () => {
    render(
      <AppShell user={USER}>
        <p>page body</p>
      </AppShell>,
      { wrapper },
    );

    const sidebar = screen.getByRole("navigation", { name: "Main navigation" });
    for (const [section, page] of [
      ["Overview", "Dashboard"],
      ["Your money", "Transactions"],
      ["Buy now, pay later", "Risk check"],
      ["How it works", "Security drill"],
    ]) {
      const list = within(sidebar).getByRole("list", { name: section });
      expect(within(list).getByRole("link", { name: new RegExp(page, "i") })).toBeInTheDocument();
    }
  });

  it("shows who is signed in, with their data and a way out", () => {
    render(
      <AppShell user={USER}>
        <p>page body</p>
      </AppShell>,
      { wrapper },
    );

    expect(screen.getByText("amir")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument(); // the initials avatar
    expect(screen.getByRole("link", { name: "Your data" })).toHaveAttribute("href", "/account");
  });

  it("keeps every other screen reachable on a phone under More, in one navigation", async () => {
    render(
      <AppShell user={USER}>
        <p>page body</p>
      </AppShell>,
      { wrapper },
    );

    expect(screen.queryByRole("navigation", { name: "More pages" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /more/i }));
    const more = screen.getByRole("dialog", { name: "Menu" });
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
    expect(post).toHaveBeenCalledWith("/api/auth/logout"); // the server ends every session too
  });
});

describe("navigation loading", () => {
  it("does not prefetch every page on screen; a page loads when its link is hovered", async () => {
    prefetch.mockClear();
    render(
      <AppShell user={USER}>
        <p>page body</p>
      </AppShell>,
      { wrapper },
    );

    expect(prefetch).not.toHaveBeenCalled();
    const sidebar = screen.getByRole("navigation", { name: "Main navigation" });
    await userEvent.hover(within(sidebar).getByRole("link", { name: /budgets/i }));
    expect(prefetch).toHaveBeenCalledWith("/budgets");
  });
});

describe("Intro replay", () => {
  beforeEach(() => signIn());

  it("replays the intro from the profile as a full-screen dialog, and Close returns focus", async () => {
    render(
      <AppShell user={USER}>
        <p>page body</p>
      </AppShell>,
      { wrapper },
    );
    expect(screen.queryByRole("dialog", { name: "Welcome to PaySense" })).toBeNull();

    const replay = screen.getAllByRole("button", { name: "Show the intro again" })[0];
    await userEvent.click(replay);
    const tour = await screen.findByRole("dialog", { name: "Welcome to PaySense" });
    expect(within(tour).getByText("Step 1 of 5")).toBeInTheDocument();
    await userEvent.click(within(tour).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog", { name: "Welcome to PaySense" })).toBeNull();
    expect(replay).toHaveFocus();
  });
});

describe("Guided tour", () => {
  beforeEach(() => signIn());

  it("opens once on the dashboard after the intro, over an inert app, and Skip ends it for good", async () => {
    window.localStorage.removeItem("paysense.tour.seen");
    // jsdom lays nothing out; give the marked controls a box so the tour has something to point at.
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      top: 10, left: 10, right: 130, bottom: 50, width: 120, height: 40, x: 10, y: 10, toJSON: () => ({}),
    });
    render(
      <AppShell user={USER}>
        <p>page body</p>
      </AppShell>,
      { wrapper },
    );
    const tour = await screen.findByRole("dialog", { name: "Tour of PaySense" });
    expect(tour).toHaveTextContent("Start here");
    expect(screen.getByText("page body").closest("[inert]")).not.toBeNull();
    await userEvent.click(within(tour).getByRole("button", { name: "Skip tour" }));
    expect(screen.queryByRole("dialog", { name: "Tour of PaySense" })).toBeNull();
    expect(tourSeen()).toBe(true);
    vi.restoreAllMocks();
  });
});

describe("Sidebar tooltips", () => {
  beforeEach(() => signIn());

  it("describes a page on hover and keyboard focus, and Escape hides it", async () => {
    render(
      <AppShell user={USER}>
        <p>page body</p>
      </AppShell>,
      { wrapper },
    );
    const sidebar = screen.getByRole("navigation", { name: "Main navigation" });
    const link = within(sidebar).getByRole("link", { name: "Budgets" });
    expect(link).toHaveAccessibleDescription(/spending limit/i);
    expect(screen.queryByRole("tooltip")).toBeNull();

    await userEvent.hover(link);
    expect(screen.getByRole("tooltip")).toHaveTextContent(/spending limit/i);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("tooltip")).toBeNull();
    await userEvent.unhover(link);

    act(() => link.focus());
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    act(() => link.blur());
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});
