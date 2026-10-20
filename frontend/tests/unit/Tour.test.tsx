import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Tour } from "@/components/onboarding/Tour";

// jsdom lays nothing out: give every marked element a box, except one marked as off screen.
function layOut() {
  return vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (
    this: HTMLElement,
  ) {
    const on = this.dataset.tour && !this.hasAttribute("data-offscreen");
    const size = on ? { width: 120, height: 40 } : { width: 0, height: 0 };
    return { top: 100, left: 20, right: 20 + size.width, bottom: 100 + size.height, x: 20, y: 100, ...size, toJSON: () => ({}) };
  });
}

function targets() {
  return (
    <>
      <div data-tour="forecast" />
      <button data-tour="import">Import</button>
      <button data-tour="risk" data-offscreen>Risk</button>
      <button data-tour="risk">Risk</button>
      <button data-tour="ask">Ask</button>
      {/* "data" is not on screen at all, so that stop is left out */}
    </>
  );
}

describe("guided tour", () => {
  beforeEach(() => void layOut());
  afterEach(() => vi.restoreAllMocks());

  it("points at each control on screen in turn, skipping the ones that are not", async () => {
    const onDone = vi.fn();
    const { rerender } = render(targets());
    rerender(
      <>
        {targets()}
        <Tour onDone={onDone} />
      </>,
    );

    const tour = screen.getByRole("dialog", { name: "Tour of PaySense" });
    expect(tour).toHaveTextContent("1 of 4");
    expect(screen.getByRole("heading", { name: "Where your money is heading" })).toHaveFocus();

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.keyboard("{ArrowRight}{ArrowRight}");
    expect(tour).toHaveTextContent("4 of 4");
    expect(screen.getByRole("heading", { name: "Ask PaySense" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(tour).toHaveTextContent("3 of 4");
    await userEvent.keyboard("{ArrowRight}");
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(onDone).toHaveBeenCalledOnce();
  });

  it("walks the main path in six stops when everything is on screen", async () => {
    render(
      <>
        {["forecast", "import", "transactions", "risk", "ask", "data"].map((t) => (
          <button key={t} data-tour={t}>
            {t}
          </button>
        ))}
      </>,
    );
    const { rerender } = render(<></>);
    rerender(<Tour onDone={vi.fn()} />);

    const titles = [];
    for (let i = 0; i < 6; i++) {
      titles.push(screen.getByRole("heading", { level: 2 }).textContent);
      // Plans is reached through the risk check's stop, not a stop of its own
      if (i === 3) expect(screen.getByText(/save it as a plan/i)).toBeInTheDocument();
      if (i < 5) await userEvent.click(screen.getByRole("button", { name: "Next" }));
    }
    expect(screen.getByRole("dialog")).toHaveTextContent("6 of 6");
    expect(titles).toEqual([
      "Where your money is heading",
      "Start here",
      "Everything you've spent",
      "Check before you split",
      "Ask PaySense",
      "Your data",
    ]);
  });

  it("ends on Skip or Escape, and at once when there is nothing to point at", async () => {
    const onDone = vi.fn();
    const { rerender, unmount } = render(targets());
    rerender(
      <>
        {targets()}
        <Tour onDone={onDone} />
      </>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Skip tour" }));
    await userEvent.keyboard("{Escape}");
    expect(onDone).toHaveBeenCalledTimes(2);

    unmount();
    const nothing = vi.fn();
    render(<Tour onDone={nothing} />);
    expect(nothing).toHaveBeenCalledOnce();
  });
});
