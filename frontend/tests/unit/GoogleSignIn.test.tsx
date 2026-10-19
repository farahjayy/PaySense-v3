import { render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GoogleSignIn } from "@/components/auth/GoogleSignIn";
import { clearSession, getSession } from "@/lib/session";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

const post = vi.fn();
vi.mock("@/lib/api/client", () => ({
  API_BASE_URL: "https://api.example.test",
  api: { POST: (...args: unknown[]) => post(...args) },
}));

const SESSION = {
  data: {
    access_token: "tok-g",
    token_type: "bearer",
    expires_in: 3600,
    user: { id: "u9", username: "g-0123456789abcdef", display_name: "Nur", persona: null },
  },
  error: undefined,
};

function visit(url: string) {
  window.history.replaceState(null, "", url);
}

describe("GoogleSignIn", () => {
  beforeEach(() => {
    replace.mockReset();
    post.mockReset();
    clearSession();
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_SIGNIN", "true");
    visit("/login");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("is a plain link to the API's Google start, not a fetch", () => {
    render(<GoogleSignIn />);

    const link = screen.getByRole("link", { name: /continue with google/i });
    expect(link).toHaveAttribute("href", "https://api.example.test/api/auth/google");
  });

  it("renders nothing when Google sign-in is not switched on", () => {
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_SIGNIN", "");
    const { container } = render(<GoogleSignIn />);

    expect(container).toBeEmptyDOMElement();
  });

  it("exchanges the one-time code once, forgets it, and signs in", async () => {
    post.mockResolvedValue(SESSION);
    visit("/login#google=one-time-code");

    render(<GoogleSignIn />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith("/api/auth/google/exchange", {
      body: { code: "one-time-code" },
    });
    expect(window.location.hash).toBe("");
    expect(getSession()?.user.display_name).toBe("Nur");
  });

  it("says so when the code has expired", async () => {
    post.mockResolvedValue({
      data: undefined,
      error: { detail: { code: "invalid_code", message: "That sign-in has expired." } },
    });
    visit("/login#google=stale");

    render(<GoogleSignIn />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/expired/i);
    expect(replace).not.toHaveBeenCalled();
    expect(getSession()).toBeNull();
  });

  it.each([
    ["cancelled", /cancelled/i],
    ["state", /expired/i],
    ["too_many", /too many/i],
    ["token", /google sign-in failed/i],
    ["anything-else", /google sign-in failed/i],
  ])("explains ?error=%s from the callback", async (reason, message) => {
    visit(`/login?error=${reason}`);

    render(<GoogleSignIn />);

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(post).not.toHaveBeenCalled();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<GoogleSignIn />);

    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });

    expect(results.violations.map((violation) => violation.id)).toEqual([]);
  });
});
