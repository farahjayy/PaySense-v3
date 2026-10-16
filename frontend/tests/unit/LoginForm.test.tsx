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

  it("keeps keyboard focus on the field while signing in (read-only, not disabled)", async () => {
    post.mockReturnValue(new Promise(() => {}));
    render(<LoginForm />);
    const input = screen.getByLabelText(/username/i);

    await userEvent.type(input, "amir{enter}");

    expect(input).toHaveAttribute("readonly");
    expect(input).not.toBeDisabled();
    expect(input).toHaveFocus();
  });

  it("ties the hint and the error to the field for screen readers", async () => {
    post.mockResolvedValue({
      data: undefined,
      error: { detail: { code: "unknown_username", message: "No account with that username." } },
    });
    render(<LoginForm />);
    const input = screen.getByLabelText(/username/i);

    const before = input.getAttribute("aria-describedby") ?? "";
    expect(document.getElementById(before)).toHaveTextContent(/username from your invite/i);

    await userEvent.type(input, "ghost");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    await screen.findByRole("alert");

    const ids = (input.getAttribute("aria-describedby") ?? "").split(" ");
    const described = ids.map((id) => document.getElementById(id)?.textContent ?? "").join(" ");
    expect(described).toMatch(/username from your invite/i);
    expect(described).toMatch(/no account with that username/i);
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("tells a tester who lost their username who to message", () => {
    render(<LoginForm />);

    expect(screen.getByText(/lost it\?/i)).toHaveTextContent(/message farah/i);
  });

  it("hides what was typed on request and shows it again", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);
    const input = screen.getByLabelText(/username/i);
    const toggle = screen.getByRole("button", { name: /hide text/i });
    expect(input).toHaveAttribute("type", "text");
    expect(toggle).toHaveAttribute("aria-pressed", "false");

    await user.type(input, "amir");
    await user.click(toggle);

    expect(input).toHaveAttribute("type", "password");
    expect(input).toHaveValue("amir");
    expect(toggle).toHaveAttribute("aria-pressed", "true");

    await user.click(toggle);
    expect(input).toHaveAttribute("type", "text");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
  });

  it("does not submit the form when the hide toggle is pressed", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);

    await user.type(screen.getByLabelText(/username/i), "amir");
    await user.click(screen.getByRole("button", { name: /hide text/i }));

    expect(post).not.toHaveBeenCalled();
  });

  it("clears the error as soon as the user edits the field", async () => {
    post.mockResolvedValue({
      data: undefined,
      error: { detail: { code: "unknown_username", message: "No account with that username." } },
    });
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText(/username/i), "ghost");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    await screen.findByRole("alert");

    await userEvent.type(screen.getByLabelText(/username/i), "x");

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
