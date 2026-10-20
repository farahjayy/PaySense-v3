import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingGate } from "@/components/onboarding/Onboarding";
import { introSeen } from "@/lib/introTour";

import { CONSENT, fail, ok, wrapper } from "./topicTestUtils";

const get = vi.fn();
const post = vi.fn();
vi.mock("@/lib/api/client", () => ({
  api: {
    GET: (...a: unknown[]) => get(...a),
    POST: (...a: unknown[]) => post(...a),
  },
}));

const ACCEPTED = { ...CONSENT, accepted: true, accepted_at: "2026-10-18T10:00:00Z" };

function gate() {
  return render(
    <OnboardingGate>
      <p>the app</p>
    </OnboardingGate>,
    { wrapper },
  );
}

describe("onboarding on first login", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    window.localStorage.clear(); // this browser has not seen the intro
  });

  it("walks a new user through the slides, the notice and a finish, before the app", async () => {
    get.mockResolvedValue(ok(CONSENT));
    post.mockResolvedValue(ok(ACCEPTED));
    gate();

    const flow = await screen.findByRole("region", { name: "Getting to know PaySense" });
    expect(within(flow).getByText("Step 1 of 6")).toBeInTheDocument();
    expect(screen.queryByText("the app")).toBeNull();

    await userEvent.click(within(flow).getByRole("button", { name: "Next" }));
    expect(within(flow).getByText("Step 2 of 6")).toBeInTheDocument();
    await userEvent.keyboard("{ArrowRight}{ArrowRight}");
    expect(within(flow).getByText("Step 4 of 6")).toBeInTheDocument();
    await userEvent.keyboard("{ArrowLeft}");
    expect(within(flow).getByText("Step 3 of 6")).toBeInTheDocument();
    await userEvent.click(within(flow).getByRole("button", { name: "Back" }));
    expect(within(flow).getByText("Step 2 of 6")).toBeInTheDocument();

    // Skip lands on the notice, which cannot be skipped or arrowed past.
    await userEvent.click(within(flow).getByRole("button", { name: "Skip" }));
    expect(within(flow).getByRole("heading", { name: "Before you start" })).toBeInTheDocument();
    expect(within(flow).getByText(/Google \(Gemini API\)/)).toBeInTheDocument();
    expect(within(flow).queryByRole("button", { name: "Skip" })).toBeNull();
    await userEvent.keyboard("{ArrowRight}");
    expect(within(flow).getByText("Step 5 of 6")).toBeInTheDocument();

    await userEvent.click(within(flow).getByRole("button", { name: /i understand/i }));
    expect(post).toHaveBeenCalledWith("/api/account/consent", { body: { version: "v1" } });
    expect(await within(flow).findByText("Step 6 of 6")).toBeInTheDocument();
    expect(within(flow).getByRole("link", { name: "Import a statement" })).toHaveAttribute(
      "href",
      "/import",
    );
    await userEvent.click(within(flow).getByRole("link", { name: "Go to the dashboard" }));
    expect(await screen.findByText("the app")).toBeInTheDocument();
    expect(introSeen()).toBe(true);
  });

  it("asks only for the notice when the slides were already seen in this browser", async () => {
    window.localStorage.setItem("paysense.intro.seen", "1");
    get.mockResolvedValue(ok(CONSENT));
    gate();
    const flow = await screen.findByRole("region", { name: "Getting to know PaySense" });
    expect(within(flow).getByText("Step 1 of 2")).toBeInTheDocument();
    expect(within(flow).getByRole("heading", { name: "Before you start" })).toBeInTheDocument();
  });

  it("shows only the slides when the notice is already accepted, and Skip ends it", async () => {
    get.mockResolvedValue(ok(ACCEPTED));
    gate();
    const flow = await screen.findByRole("region", { name: "Getting to know PaySense" });
    expect(within(flow).getByText("Step 1 of 5")).toBeInTheDocument();
    await userEvent.click(within(flow).getByRole("button", { name: "Skip" }));
    expect(await screen.findByText("the app")).toBeInTheDocument();
    expect(introSeen()).toBe(true);
  });

  it("opens the app straight away once everything is done, or if the notice cannot load", async () => {
    window.localStorage.setItem("paysense.intro.seen", "1");
    get.mockResolvedValue(ok(ACCEPTED));
    const { unmount } = gate();
    expect(await screen.findByText("the app")).toBeInTheDocument();
    unmount();

    get.mockResolvedValue(fail(500, "internal_error", "Nope"));
    gate();
    expect(await screen.findByText("the app")).toBeInTheDocument();
  });
});
