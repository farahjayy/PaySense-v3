import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/AppShell";
import { AuthGate } from "@/components/auth/AuthGate";
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

describe("Intro tour", () => {
  beforeEach(() => {
    signIn();
    window.localStorage.clear(); // a first visit in this browser
  });

  function shell() {
    return render(
      <AppShell user={USER}>
        <p>page body</p>
      </AppShell>,
      { wrapper },
    );
  }

  it("opens on a first visit and steps through four slides with buttons and arrow keys", async () => {
    shell();
    const tour = await screen.findByRole("dialog", { name: "Welcome to PaySense" });
    expect(within(tour).getByText("Step 1 of 4")).toBeInTheDocument();
    expect(within(tour).queryByRole("button", { name: "Back" })).toBeNull();

    await userEvent.click(within(tour).getByRole("button", { name: "Next" }));
    expect(within(tour).getByText("Step 2 of 4")).toBeInTheDocument();
    await userEvent.keyboard("{ArrowRight}");
    expect(within(tour).getByText("Step 3 of 4")).toBeInTheDocument();
    await userEvent.keyboard("{ArrowLeft}");
    expect(within(tour).getByText("Step 2 of 4")).toBeInTheDocument();
    await userEvent.click(within(tour).getByRole("button", { name: "Back" }));
    expect(within(tour).getByText("Step 1 of 4")).toBeInTheDocument();
  });

  it("ends with Import and Look around; Look around closes it for good", async () => {
    const { unmount } = shell();
    const tour = await screen.findByRole("dialog", { name: "Welcome to PaySense" });
    for (let i = 0; i < 3; i++) {
      await userEvent.click(within(tour).getByRole("button", { name: "Next" }));
    }
    expect(within(tour).getByText("Step 4 of 4")).toBeInTheDocument();
    expect(within(tour).getByRole("link", { name: "Import a statement" })).toHaveAttribute(
      "href",
      "/import",
    );
    await userEvent.click(within(tour).getByRole("button", { name: "Look around" }));
    expect(screen.queryByRole("dialog", { name: "Welcome to PaySense" })).toBeNull();

    unmount();
    shell();
    await screen.findByText("page body");
    expect(screen.queryByRole("dialog", { name: "Welcome to PaySense" })).toBeNull();
  });

  it("can be skipped from any slide and replayed from the profile", async () => {
    shell();
    const tour = await screen.findByRole("dialog", { name: "Welcome to PaySense" });
    await userEvent.click(within(tour).getByRole("button", { name: "Skip" }));
    expect(screen.queryByRole("dialog", { name: "Welcome to PaySense" })).toBeNull();

    const replay = screen.getByRole("button", { name: "Show the intro again" });
    await userEvent.click(replay);
    const again = await screen.findByRole("dialog", { name: "Welcome to PaySense" });
    expect(within(again).getByText("Step 1 of 4")).toBeInTheDocument();
    await userEvent.click(within(again).getByRole("button", { name: "Close" }));
    expect(replay).toHaveFocus();
  });
});
