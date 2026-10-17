import { render, screen, within } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/login/page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));
vi.mock("@/lib/api/client", () => ({ api: { POST: vi.fn() } }));

describe("LoginPage", () => {
  it("says what PaySense does in one headline and one line", () => {
    render(<LoginPage />);

    expect(
      screen.getByRole("heading", { level: 2, name: "Think before you split." }),
    ).toBeVisible();
    expect(
      screen.getByText("Instantly check if a BNPL instalment fits into your monthly spending."),
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
    expect(screen.getByRole("heading", { level: 1, name: "Welcome" })).toBeVisible();
    expect(screen.getByLabelText(/username/i)).toBeVisible();
  });

  it("asks for the passphrase and says what PaySense is not", () => {
    render(<LoginPage />);

    expect(screen.getByText("Enter your username and passphrase to start.")).toBeVisible();
    expect(screen.queryByText(/there is no password/i)).toBeNull();
    const note = screen.getByText(/not financial advice/i);
    expect(note).toHaveTextContent(/not a credit decision/i);
    expect(note).toHaveTextContent(/nothing changes until you confirm/i);
  });

  it("explains the local terms for readers outside Malaysia", () => {
    const { container } = render(<LoginPage />);

    const box = container.querySelector("details");
    expect(box).not.toBeNull();
    expect(within(box as HTMLElement).getByText(/new to BNPL in Malaysia/i)).toBeInTheDocument();
    for (const term of [/ringgit/i, /SPayLater/, /TikTok PayLater/, /Atome/, /PTPTN/]) {
      expect(box).toHaveTextContent(term);
    }
  });

  it("does not show any figure that is not the user's own", () => {
    const { container } = render(<LoginPage />);

    expect(container.textContent).not.toMatch(/RM\s?\d|\d+%|\d{2,}/);
  });

  it("has no automated accessibility violations (contrast is checked from the tokens)", async () => {
    const { container } = render(<LoginPage />);

    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });

    expect(results.violations.map((violation) => violation.id)).toEqual([]);
  });
});
