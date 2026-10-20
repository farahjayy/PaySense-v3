import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/LoginForm";
import { getSession, saveSession } from "@/lib/session";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

const post = vi.fn();
vi.mock("@/lib/api/client", () => ({ api: { POST: (...args: unknown[]) => post(...args) } }));

const PASSPHRASE = "correct horse battery staple";

/** Fill both fields: the identifier (as given) and the shared test password. */
async function fill(username: string) {
  await userEvent.type(screen.getByLabelText("Email or username"), username);
  await userEvent.type(screen.getByLabelText("Password"), PASSPHRASE);
}

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

  it("keeps the button disabled until an email or username and a password are typed", async () => {
    render(<LoginForm />);

    const button = screen.getByRole("button", { name: "Sign in" });
    expect(button).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Email or username"), "amir");
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Password"), PASSPHRASE);
    expect(button).toBeEnabled();
  });

  it("keeps the password hidden unless asked, and never trims it", async () => {
    const user = userEvent.setup();
    post.mockResolvedValue(LOGIN_OK);
    render(<LoginForm />);
    const field = screen.getByLabelText("Password");
    expect(field).toHaveAttribute("type", "password");
    expect(field).toHaveAttribute("autocomplete", "current-password");

    await user.click(screen.getByRole("button", { name: /show password/i }));
    expect(field).toHaveAttribute("type", "text");

    await user.type(screen.getByLabelText("Email or username"), "amir");
    await user.type(field, " spaced words ok ");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(post).toHaveBeenCalledWith("/api/auth/login", {
      body: { username: "amir", passphrase: " spaced words ok " },
    });
  });

  it("stores the session and goes to the dashboard on success", async () => {
    post.mockResolvedValue(LOGIN_OK);
    render(<LoginForm />);

    await fill("  amir ");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(post).toHaveBeenCalledWith("/api/auth/login", {
      body: { username: "amir", passphrase: PASSPHRASE },
    });
    expect(getSession()?.user.display_name).toBe("Amir");
    expect(getSession()?.token).toBe("tok-1");
  });

  it("shows the server's message when the username is unknown", async () => {
    post.mockResolvedValue({
      data: undefined,
      error: {
        detail: {
          code: "invalid_credentials",
          message: "That email or username and password do not match.",
        },
      },
    });
    render(<LoginForm />);

    await fill("ghost");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("That email or username and password do not match.");
    expect(replace).not.toHaveBeenCalled();
    expect(getSession()).toBeNull();
  });

  it("explains a network failure instead of crashing", async () => {
    post.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<LoginForm />);

    await fill("amir");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

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

    await fill("amir");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(screen.getByRole("button", { name: /signing in/i })).toBeDisabled();
    resolve(LOGIN_OK);
    await waitFor(() => expect(replace).toHaveBeenCalled());
  });

  it("keeps keyboard focus on the field while signing in (read-only, not disabled)", async () => {
    post.mockReturnValue(new Promise(() => {}));
    render(<LoginForm />);
    const input = screen.getByLabelText("Email or username");

    await userEvent.type(screen.getByLabelText("Password"), PASSPHRASE);
    await userEvent.type(input, "amir{enter}");

    expect(input).toHaveAttribute("readonly");
    expect(input).not.toBeDisabled();
    expect(input).toHaveFocus();
  });

  it("ties the hint and the error to the field for screen readers", async () => {
    post.mockResolvedValue({
      data: undefined,
      error: {
        detail: {
          code: "invalid_credentials",
          message: "That email or username and password do not match.",
        },
      },
    });
    render(<LoginForm />);
    const input = screen.getByLabelText("Email or username");

    const before = input.getAttribute("aria-describedby") ?? "";
    expect(document.getElementById(before)).toHaveTextContent(/invite from the team/i);

    await userEvent.type(input, "ghost");
    await userEvent.type(screen.getByLabelText("Password"), PASSPHRASE);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByRole("alert");

    const ids = (input.getAttribute("aria-describedby") ?? "").split(" ");
    const described = ids.map((id) => document.getElementById(id)?.textContent ?? "").join(" ");
    expect(described).toMatch(/invite from the team/i);
    expect(described).toMatch(/username and password do not match/i);
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("clears the error as soon as the user edits the field", async () => {
    post.mockResolvedValue({
      data: undefined,
      error: {
        detail: {
          code: "invalid_credentials",
          message: "That email or username and password do not match.",
        },
      },
    });
    render(<LoginForm />);
    await fill("ghost");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByRole("alert");

    await userEvent.type(screen.getByLabelText("Email or username"), "x");

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  describe("creating an account", () => {
    const SIGNUP_OK = {
      data: { ...LOGIN_OK.data, user: { ...LOGIN_OK.data.user, email: "nur@example.com" } },
      error: undefined,
    };

    it("asks for a name, an email and a password of at least 12 characters", async () => {
      render(<LoginForm mode="signup" />);
      const button = screen.getByRole("button", { name: "Create account" });
      expect(screen.getByLabelText("Email")).toHaveAttribute("type", "email");
      expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "new-password");
      expect(screen.getByText(/at least 12 characters/i)).toBeInTheDocument();

      await userEvent.type(screen.getByLabelText("Your name"), "Nur");
      await userEvent.type(screen.getByLabelText("Email"), "nur@example.com");
      await userEvent.type(screen.getByLabelText("Password"), "too short");
      expect(button).toBeDisabled();
      await userEvent.type(screen.getByLabelText("Password"), " no more");
      expect(button).toBeEnabled();
    });

    it("creates the account, stores the session and goes to the dashboard", async () => {
      post.mockResolvedValue(SIGNUP_OK);
      render(<LoginForm mode="signup" />);

      await userEvent.type(screen.getByLabelText("Your name"), " Nur ");
      await userEvent.type(screen.getByLabelText("Email"), " nur@example.com ");
      await userEvent.type(screen.getByLabelText("Password"), PASSPHRASE);
      await userEvent.click(screen.getByRole("button", { name: "Create account" }));

      await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
      expect(post).toHaveBeenCalledWith("/api/auth/signup", {
        body: { email: "nur@example.com", password: PASSPHRASE, display_name: "Nur" },
      });
      expect(getSession()?.user.email).toBe("nur@example.com");
    });

    it("shows the server's message when the email is already used", async () => {
      post.mockResolvedValue({
        data: undefined,
        error: { detail: { code: "email_taken", message: "An account with that email already exists. Sign in instead." } },
      });
      render(<LoginForm mode="signup" />);

      await userEvent.type(screen.getByLabelText("Your name"), "Nur");
      await userEvent.type(screen.getByLabelText("Email"), "nur@example.com");
      await userEvent.type(screen.getByLabelText("Password"), PASSPHRASE);
      await userEvent.click(screen.getByRole("button", { name: "Create account" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(/already exists/i);
      expect(getSession()).toBeNull();
    });
  });
});
