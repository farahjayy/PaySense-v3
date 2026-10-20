import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/login/page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));
vi.mock("@/lib/api/client", () => ({
  API_BASE_URL: "http://api.test",
  api: { POST: vi.fn() },
}));

describe("LoginPage", () => {
  it("says what PaySense does in one headline and one line", () => {
    render(<LoginPage />);

    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Think before you split.",
      }),
    ).toBeVisible();
    expect(
      screen.getByText(
        "Instantly check if a BNPL instalment fits into your monthly spending.",
      ),
    ).toBeVisible();
  });

  it("previews the three results with the names the app uses", () => {
    render(<LoginPage />);

    const results = screen.getByRole("list", { name: /three results/i });
    const names = within(results)
      .getAllByRole("listitem")
      .map((item) => item.textContent);

    expect(names).toEqual(["Safe", "Caution", "At Risk"]);
  });

  it("keeps a single page heading for the sign-in form", () => {
    render(<LoginPage />);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(
      screen.getByRole("heading", { level: 1, name: "Welcome back" }),
    ).toBeVisible();
    expect(screen.getByLabelText("Email or username")).toBeVisible();
  });

  it("switches between signing in and creating an account", async () => {
    render(<LoginPage />);
    const signin = screen.getByRole("button", {
      name: "Sign in",
      pressed: true,
    });

    await userEvent.click(
      screen.getByRole("button", { name: "Create account", pressed: false }),
    );

    expect(signin).toHaveAttribute("aria-pressed", "false");
    expect(
      screen.getByRole("heading", { level: 1, name: "Create your account" }),
    ).toBeVisible();
    expect(screen.getByLabelText("Your name")).toBeVisible();
    expect(screen.getByLabelText("Email")).toHaveAttribute("type", "email");
    expect(
      screen.queryByRole("link", { name: "Continue with Google" }),
    ).toBeNull();
  });

  it("opens on Create account when linked with #signup", async () => {
    window.location.hash = "#signup";
    render(<LoginPage />);

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Create your account",
      }),
    ).toBeVisible();
    window.location.hash = "";
  });

  it("says what PaySense is not", () => {
    render(<LoginPage />);

    const note = screen.getByText(/not financial advice/i);
    expect(note).toHaveTextContent(/not a credit decision/i);
    expect(note).toHaveTextContent(/nothing changes until you confirm/i);
  });

  it("explains the local terms for readers outside Malaysia", () => {
    const { container } = render(<LoginPage />);

    const box = container.querySelector("details");
    expect(box).not.toBeNull();
    expect(
      within(box as HTMLElement).getByText(/new to BNPL in Malaysia/i),
    ).toBeInTheDocument();
    for (const term of [
      /ringgit/i,
      /SPayLater/,
      /TikTok PayLater/,
      /Atome/,
      /PTPTN/,
    ]) {
      expect(box).toHaveTextContent(term);
    }
  });

  it("does not show any figure that is not the user's own", () => {
    const { container } = render(<LoginPage />);

    expect(container.textContent).not.toMatch(/RM\s?\d|\d+%|\d{2,}/);
  });

  it("has no automated accessibility violations (contrast is checked from the tokens)", async () => {
    const { container } = render(<LoginPage />);

    const results = await axe.run(container, {
      rules: { "color-contrast": { enabled: false } },
    });

    expect(results.violations.map((violation) => violation.id)).toEqual([]);
  });

  describe("with Google sign-in on", () => {
    beforeEach(() => vi.stubEnv("NEXT_PUBLIC_GOOGLE_SIGNIN", "true"));
    afterEach(() => vi.unstubAllEnvs());

    it("offers Google under the form, after an 'or', with no test-account fold", () => {
      render(<LoginPage />);

      const google = screen.getByRole("link", { name: "Continue with Google" });
      const field = screen.getByLabelText("Email or username");
      expect(
        field.compareDocumentPosition(google) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
      expect(screen.getByText("or")).toBeVisible();
      expect(screen.queryByText("Use a test account")).toBeNull();
    });

    it("has no automated accessibility violations", async () => {
      const { container } = render(<LoginPage />);

      const results = await axe.run(container, {
        rules: { "color-contrast": { enabled: false } },
      });

      expect(results.violations.map((violation) => violation.id)).toEqual([]);
    });
  });
});
