import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import WelcomePage from "@/app/welcome/page";

describe("welcome page", () => {
  it("says what PaySense is, how it works, and leads to sign-in", () => {
    render(<WelcomePage />);
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /think before you split/i,
      }),
    ).toBeInTheDocument();
    for (const link of screen.getAllByRole("link", {
      name: /get started|sign in/i,
    })) {
      expect(link).toHaveAttribute("href", "/login");
    }
    const how = screen.getByRole("region", { name: "How it works" });
    expect(within(how).getAllByRole("listitem")).toHaveLength(3);
  });

  it("leads with the student's problem, the three answers, the providers and their control", () => {
    render(<WelcomePage />);
    expect(
      screen.getByRole("region", { name: "Small instalments add up" }),
    ).toBeInTheDocument();
    const answers = screen.getByRole("region", {
      name: "One of three answers",
    });
    expect(
      within(answers)
        .getAllByRole("listitem")
        .map((li) => li.querySelector(".lg-chip")?.textContent),
    ).toEqual(["Safe", "Caution", "At Risk"]);
    const providers = screen.getByRole("region", {
      name: "Knows the plans students use",
    });
    for (const name of ["SPayLater", "TikTok PayLater", "Atome"])
      expect(providers).toHaveTextContent(name);
    expect(
      screen.getByRole("region", { name: "You stay in control" }),
    ).toHaveTextContent(/press Confirm/);
  });

  it("closes on creating an account, which opens the sign-up tab", () => {
    render(<WelcomePage />);
    expect(
      screen.getByRole("link", { name: /create your account/i }),
    ).toHaveAttribute("href", "/login#signup");
  });

  it("shows no figure that is not traceable (no user counts, no testimonials)", () => {
    const { container } = render(<WelcomePage />);
    expect(container.textContent).not.toMatch(/RM\s?\d|\d+%|\d{2,}/);
  });
});
