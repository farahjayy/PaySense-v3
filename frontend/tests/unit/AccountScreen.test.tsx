import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConsentGate } from "@/components/account/ConsentNotice";
import { AlertStrip } from "@/components/dashboard/AlertStrip";
import { AccountScreen } from "@/components/screens/AccountScreen";

import { CONSENT, fail, ok, RECS, wrapper } from "./topicTestUtils";

const get = vi.fn();
const post = vi.fn();
const put = vi.fn();
vi.mock("@/lib/api/client", () => ({
  api: {
    GET: (...a: unknown[]) => get(...a),
    POST: (...a: unknown[]) => post(...a),
    PUT: (...a: unknown[]) => put(...a),
  },
}));

describe("first-login consent", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it("shows the notice instead of the app until it is accepted", async () => {
    get.mockResolvedValue(ok(CONSENT));
    post.mockResolvedValue(ok({ ...CONSENT, accepted: true, accepted_at: "2026-10-18T10:00:00Z" }));
    render(
      <ConsentGate>
        <p>the app</p>
      </ConsentGate>,
      { wrapper },
    );
    expect(await screen.findByRole("heading", { name: "Before you start" })).toBeInTheDocument();
    expect(screen.getByText(/Google \(Gemini API\)/)).toBeInTheDocument();
    expect(screen.queryByText("the app")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /i understand/i }));
    expect(post).toHaveBeenCalledWith("/api/account/consent", { body: { version: "v1" } });
    expect(await screen.findByText("the app")).toBeInTheDocument();
  });

  it("opens the app straight away once accepted, or if the notice cannot load", async () => {
    get.mockResolvedValue(ok({ ...CONSENT, accepted: true }));
    const { unmount } = render(
      <ConsentGate>
        <p>the app</p>
      </ConsentGate>,
      { wrapper },
    );
    expect(await screen.findByText("the app")).toBeInTheDocument();
    unmount();
    get.mockResolvedValue(fail(500, "internal_error", "Nope"));
    render(
      <ConsentGate>
        <p>the app</p>
      </ConsentGate>,
      { wrapper },
    );
    expect(await screen.findByText("the app")).toBeInTheDocument();
  });
});

describe("AccountScreen", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    get.mockResolvedValue(ok({ ...CONSENT, accepted: true, accepted_at: "2026-10-18T10:00:00Z" }));
  });

  it("shows the accepted notice", async () => {
    render(<AccountScreen />, { wrapper });
    expect(
      await screen.findByText("You accepted version v1 on 18 October 2026."),
    ).toBeInTheDocument();
  });

  it("deletes only with the typed phrase and the passphrase", async () => {
    post.mockResolvedValue(
      ok({ deleted: { transactions: 3 }, message: "Your data has been deleted." }),
    );
    render(<AccountScreen />, { wrapper });
    await userEvent.click(await screen.findByRole("button", { name: "Delete my data…" }));
    const dialog = await screen.findByRole("dialog", { name: /delete all your data/i });
    const go = within(dialog).getByRole("button", { name: "Delete everything" });
    expect(go).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/type "delete my data"/i), "delete my data");
    expect(go).toBeDisabled();
    await userEvent.type(
      within(dialog).getByLabelText("Your passphrase"),
      "correct horse battery staple",
    );
    await userEvent.click(go);
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/api/account/delete", {
        body: { confirmation: "delete my data", passphrase: "correct horse battery staple" },
      }),
    );
    expect(await screen.findByText("Your data has been deleted")).toBeInTheDocument();
  });

  it("explains a wrong passphrase", async () => {
    post.mockResolvedValue(
      fail(403, "wrong_passphrase", "That passphrase is not right. Nothing was deleted."),
    );
    render(<AccountScreen />, { wrapper });
    await userEvent.click(await screen.findByRole("button", { name: "Delete my data…" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/type "delete my data"/i), "delete my data");
    await userEvent.type(within(dialog).getByLabelText("Your passphrase"), "wrong");
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete everything" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Nothing was deleted");
  });

  it("downloads the export as a file", async () => {
    post.mockResolvedValue(ok({ exported_at: "x", user: {}, settings: null, tables: {} }));
    const create = vi.fn(() => "blob:x");
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
    render(<AccountScreen />, { wrapper });
    await userEvent.click(await screen.findByRole("button", { name: "Download my data" }));
    expect(await screen.findByText("Your file is ready.")).toBeInTheDocument();
    expect(create).toHaveBeenCalled();
  });
});

describe("SavingsBuffer", () => {
  beforeEach(() => {
    get.mockReset();
    put.mockReset();
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path === "/api/settings"
          ? ok({ savings_buffer_sen: 0, onboarding_state: "complete" })
          : ok({ ...CONSENT, accepted: true }),
      ),
    );
  });

  it("saves the savings buffer in sen and says what it changes", async () => {
    put.mockResolvedValue(ok({ savings_buffer_sen: 100000, onboarding_state: "complete" }));
    render(<AccountScreen />, { wrapper });
    expect(
      await screen.findByRole("heading", { name: "Savings you could fall back on" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/forecasts and risk checks start from it/i)).toBeInTheDocument();
    await userEvent.type(await screen.findByLabelText("Savings buffer"), "1,000");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(put).toHaveBeenCalledWith("/api/settings", { body: { savings_buffer_sen: 100000 } });
    expect(await screen.findByText("Saved: RM 1,000.00.")).toBeInTheDocument();
  });

  it("clears the buffer", async () => {
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path === "/api/settings"
          ? ok({ savings_buffer_sen: 50000, onboarding_state: "complete" })
          : ok({ ...CONSENT, accepted: true }),
      ),
    );
    put.mockResolvedValue(ok({ savings_buffer_sen: 0, onboarding_state: "complete" }));
    render(<AccountScreen />, { wrapper });
    expect(await screen.findByText("Now: RM 500.00.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(put).toHaveBeenCalledWith("/api/settings", { body: { savings_buffer_sen: 0 } });
  });
});

describe("AlertStrip", () => {
  it("shows only the alerts, and nothing when there are none", async () => {
    get.mockReset();
    get.mockResolvedValue(ok({ ...RECS, items: RECS.items.filter((r) => r.is_alert) }));
    const { unmount } = render(<AlertStrip />, { wrapper });
    expect(await screen.findByText("Needs your attention")).toBeInTheDocument();
    expect(screen.getByText("Transport is over budget.")).toBeInTheDocument();
    unmount();
    get.mockResolvedValue(ok({ ...RECS, items: [] }));
    const { container } = render(<AlertStrip />, { wrapper });
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
