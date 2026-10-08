import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/LoginForm";
import { getSession, saveSession } from "@/lib/session";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

const post = vi.fn();
vi.mock("@/lib/api/client", () => ({ api: { POST: (...args: unknown[]) => post(...args) } }));

const LOGIN_OK = {
  data: {
    access_token: "tok-1",
    token_type: "bearer",
    expires_in: 3600,
    user: { id: "u1", username: "amir", display_name: "Amir", persona: "frequent_bnpl" },
  },
  error: undefined,
};

describe("LoginForm", () => {
  beforeEach(() => {
    replace.mockReset();
    post.mockReset();
  });

  it("keeps the button disabled until a username is typed", async () => {
    render(<LoginForm />);

    const button = screen.getByRole("button", { name: /continue/i });
    expect(button).toBeDisabled();

    await userEvent.type(screen.getByLabelText(/username/i), "amir");
    expect(button).toBeEnabled();
  });

  it("stores the session and goes to the dashboard on success", async () => {
    post.mockResolvedValue(LOGIN_OK);
    render(<LoginForm />);

    await userEvent.type(screen.getByLabelText(/username/i), "  amir ");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(post).toHaveBeenCalledWith("/api/auth/login", { body: { username: "amir" } });
    expect(getSession()?.user.display_name).toBe("Amir");
    expect(getSession()?.token).toBe("tok-1");
  });

  it("shows the server's message when the username is unknown", async () => {
    post.mockResolvedValue({
      data: undefined,
      error: { detail: { code: "unknown_username", message: "No account with that username." } },
    });
    render(<LoginForm />);

    await userEvent.type(screen.getByLabelText(/username/i), "ghost");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No account with that username.");
    expect(replace).not.toHaveBeenCalled();
    expect(getSession()).toBeNull();
  });

  it("explains a network failure instead of crashing", async () => {
    post.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<LoginForm />);

    await userEvent.type(screen.getByLabelText(/username/i), "amir");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/can't reach the server/i);
  });

  it("sends an already signed-in visitor straight to the dashboard", async () => {
    saveSession({
      token: "tok-1",
      expiresAt: Date.now() + 60_000,
      user: { id: "u1", username: "amir", display_name: "Amir", persona: null },
    });

    render(<LoginForm />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });

  it("disables the form while the request is in flight", async () => {
    let resolve: (value: unknown) => void = () => {};
    post.mockReturnValue(new Promise((r) => (resolve = r)));
    render(<LoginForm />);

    await userEvent.type(screen.getByLabelText(/username/i), "amir");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));

    expect(screen.getByRole("button", { name: /signing in/i })).toBeDisabled();
    resolve(LOGIN_OK);
    await waitFor(() => expect(replace).toHaveBeenCalled());
  });
});
