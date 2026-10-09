import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ModelScreen } from "@/components/screens/ModelScreen";

describe("ModelScreen", () => {
  it("never shows internal engine names to the user", () => {
    const { container } = render(<ModelScreen />);
    expect(container.textContent).not.toMatch(/engine\s*[12]/i);
  });

  it("states the band cut-offs and the known weaknesses", () => {
    render(<ModelScreen />);
    expect(screen.getByText(/under a 10% chance/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /where it is weak/i })).toBeInTheDocument();
    expect(screen.getByText(/savings you hold are not counted/i)).toBeInTheDocument();
    expect(screen.getByText(/not financial advice/i)).toBeInTheDocument();
  });

  it("has one h1 and every section is a labelled region", () => {
    render(<ModelScreen />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    for (const name of [
      /financial health forecast/i,
      /bnpl risk check/i,
      /what it was built from/i,
    ]) {
      expect(screen.getByRole("region", { name })).toBeInTheDocument();
    }
  });
});
