import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Banner } from "@/components/ui/Banner";
import { BandBadge } from "@/components/ui/BandBadge";
import { Dialog } from "@/components/ui/Dialog";
import { MoneyInput } from "@/components/ui/MoneyInput";
import { ScoreRing } from "@/components/ui/ScoreRing";
import { EmptyState, ErrorState, LockedState, Skeleton } from "@/components/ui/States";
import { StatTile } from "@/components/ui/StatTile";

describe("Banner", () => {
  it("announces a danger message immediately and the rest politely", () => {
    const { rerender } = render(<Banner tone="danger">Boom</Banner>);
    expect(screen.getByRole("alert")).toHaveTextContent("Boom");

    rerender(<Banner tone="warning">Careful</Banner>);
    expect(screen.getByRole("status")).toHaveTextContent("Careful");
  });

  it("gives every tone a glyph so colour is not the only signal", () => {
    for (const tone of ["info", "success", "warning", "danger"] as const) {
      const { container, unmount } = render(<Banner tone={tone}>x</Banner>);
      expect(container.querySelector("[aria-hidden]")?.textContent?.length).toBeGreaterThan(0);
      unmount();
    }
  });

  it("shows a title above the body when given one", () => {
    render(<Banner title="Heads up">Detail</Banner>);

    expect(screen.getByText("Heads up")).toBeInTheDocument();
    expect(screen.getByText("Detail")).toBeInTheDocument();
  });
});

describe("BandBadge", () => {
  it.each(["Safe", "Caution", "At Risk"] as const)("names %s in words, with a glyph", (band) => {
    render(<BandBadge band={band} />);

    expect(screen.getByText(band, { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Risk level:")).toHaveClass("sr-only");
  });
});

describe("ScoreRing", () => {
  it("states the score and band in its accessible name", () => {
    render(<ScoreRing score={77} band="Safe" />);

    expect(screen.getByRole("img", { name: "Score 77 out of 100, Safe" })).toBeInTheDocument();
  });

  it("keeps an out-of-range score inside 0 to 100", () => {
    render(<ScoreRing score={140} band="Safe" />);

    expect(screen.getByRole("img")).toHaveAccessibleName("Score 100 out of 100, Safe");
  });
});

describe("states", () => {
  it("marks a skeleton as busy for assistive technology", () => {
    render(<Skeleton label="Loading forecast" />);

    expect(screen.getByRole("status", { name: "Loading forecast" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });

  it("offers the next step from an empty state", () => {
    render(<EmptyState title="No plans yet" action={<button>Add one</button>} />);

    expect(screen.getByRole("button", { name: "Add one" })).toBeInTheDocument();
  });

  it("explains an error and lets the person retry", async () => {
    const retry = vi.fn();
    render(<ErrorState message="Can't reach the server." onRetry={retry} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Can't reach the server.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("shows progress toward four months and links to the import", () => {
    render(<LockedState reason="needs_four_months" monthsOfHistory={2} />);

    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
    expect(screen.getByText("2 months of 4 logged")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Import a statement" })).toHaveAttribute(
      "href",
      "/import",
    );
  });

  it("caps the months shown at four and says something different when nothing is usable", () => {
    const { rerender } = render(<LockedState reason="needs_four_months" monthsOfHistory={9} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "4");
    // Enough months but not enough weeks is a different message, not "needs four months".
    expect(screen.getByText(/needs a few more complete weeks/i)).toBeInTheDocument();
    expect(screen.queryByText(/unlocks with four months/i)).not.toBeInTheDocument();

    rerender(<LockedState reason="no_usable_history" monthsOfHistory={5} />);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.getByText("There is nothing to forecast from yet")).toBeInTheDocument();
  });
});

describe("StatTile", () => {
  it("shows the label, the value and the qualifying note", () => {
    render(<StatTile label="Worst month" value="July 2025" note="Most likely to run short" />);

    expect(screen.getByText("Worst month")).toBeInTheDocument();
    expect(screen.getByText("July 2025")).toBeInTheDocument();
    expect(screen.getByText("Most likely to run short")).toBeInTheDocument();
  });
});

describe("MoneyInput", () => {
  it("reports whole sen parsed from the typed text", async () => {
    const onChange = vi.fn();
    render(<MoneyInput label="Price" valueSen={null} onChange={onChange} />);

    await userEvent.type(screen.getByLabelText("Price"), "19.99");

    expect(onChange).toHaveBeenLastCalledWith(1999);
  });

  it("reports null while the field is empty or not an amount, and explains it once left", async () => {
    const onChange = vi.fn();
    render(<MoneyInput label="Price" valueSen={null} onChange={onChange} />);
    const field = screen.getByLabelText("Price");

    await userEvent.type(field, "12.345");
    expect(onChange).toHaveBeenLastCalledWith(null);
    await userEvent.tab();

    expect(screen.getByRole("alert")).toHaveTextContent("Enter an amount like 12.50");
    expect(field).toHaveAttribute("aria-invalid", "true");
  });

  it("starts from an existing value", () => {
    render(<MoneyInput label="Limit" valueSen={250000} onChange={() => undefined} />);

    expect(screen.getByLabelText("Limit")).toHaveValue("2,500.00");
  });

  it("shows an error from the server beside the field", () => {
    render(
      <MoneyInput label="Price" valueSen={100} onChange={() => undefined} error="Too large" />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Too large");
  });
});

describe("Dialog", () => {
  it("renders its content only while open and names itself by its title", () => {
    const { rerender } = render(
      <Dialog open={false} title="Add transaction" onClose={() => undefined}>
        <p>Body</p>
      </Dialog>,
    );
    expect(screen.queryByText("Body")).not.toBeInTheDocument();

    rerender(
      <Dialog open title="Add transaction" onClose={() => undefined}>
        <p>Body</p>
      </Dialog>,
    );
    expect(screen.getByText("Body")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Add transaction" })).toBeInTheDocument();
  });

  it("closes from its close button", async () => {
    const onClose = vi.fn();
    render(
      <Dialog open title="Add" onClose={onClose}>
        <p>Body</p>
      </Dialog>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(onClose).toHaveBeenCalledOnce();
  });
});
