import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Loading from "@/app/(app)/loading";

describe("route loading screen", () => {
  it("shows a busy placeholder while the next page loads", () => {
    render(<Loading />);
    expect(screen.getByRole("status", { name: "Loading page" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });
});
