import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import WelcomePage from "@/app/welcome/page";

describe("welcome page", () => {
  it("says what PaySense is, how it works, and leads to sign-in", () => {
    render(<WelcomePage />);
    expect(screen.getByRole("heading", { level: 1, name: /think before you split/i })).toBeInTheDocument();
    for (const link of screen.getAllByRole("link", { name: /get started|log in/i })) {
      expect(link).toHaveAttribute("href", "/login");
    }
    const how = screen.getByRole("region", { name: "How it works" });
    expect(within(how).getAllByRole("listitem")).toHaveLength(3);
  });
});
