import { describe, expect, it, vi } from "vitest";

import {
  clearSession,
  getSession,
  saveSession,
  subscribeSession,
  type Session,
} from "@/lib/session";

const NOW = 1_700_000_000_000;

function sample(overrides: Partial<Session> = {}): Session {
  return {
    token: "abc.def.ghi",
    expiresAt: NOW + 60_000,
    user: { id: "u1", username: "amir", display_name: "Amir", persona: "frequent_bnpl" },
    ...overrides,
  };
}

describe("session storage", () => {
  it("round-trips a saved session", () => {
    saveSession(sample());

    expect(getSession(NOW)).toEqual(sample());
  });

  it("returns null when nothing is stored", () => {
    expect(getSession(NOW)).toBeNull();
  });

  it("forgets the session on clear", () => {
    saveSession(sample());

    clearSession();

    expect(getSession(NOW)).toBeNull();
  });

  it("treats an expired session as absent", () => {
    saveSession(sample({ expiresAt: NOW - 1 }));

    expect(getSession(NOW)).toBeNull();
  });

  it("ignores corrupted or wrongly-shaped stored values", () => {
    window.sessionStorage.setItem("paysense.session", "{not json");
    expect(getSession(NOW)).toBeNull();

    window.sessionStorage.setItem("paysense.session", JSON.stringify({ token: 1 }));
    expect(getSession(NOW)).toBeNull();
  });

  it("returns the same object for repeated reads of unchanged storage", () => {
    saveSession(sample());

    expect(getSession(NOW)).toBe(getSession(NOW));
  });

  it("notifies subscribers on save and clear, and stops after unsubscribe", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeSession(listener);

    saveSession(sample());
    clearSession();
    expect(listener).toHaveBeenCalledTimes(2);

    unsubscribe();
    saveSession(sample());
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("does not throw when sessionStorage is unavailable", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });

    expect(getSession(NOW)).toBeNull();

    spy.mockRestore();
  });
});

describe("when sessionStorage cannot be written", () => {
  it("still lets the user log in for this tab, and reports that it did not persist", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota / private mode");
    });

    const persisted = saveSession(sample());

    expect(persisted).toBe(false);
    expect(getSession(NOW)).toEqual(sample()); // held in memory, not bounced back to /login
    spy.mockRestore();
  });

  it("reports success when storage works", () => {
    expect(saveSession(sample())).toBe(true);
  });

  it("forgets the in-memory session on clear", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    saveSession(sample());
    spy.mockRestore();

    clearSession();

    expect(getSession(NOW)).toBeNull();
  });
});

describe("persona handling", () => {
  it("accepts a persona the frontend does not know about yet", () => {
    saveSession(sample({ user: { id: "u", username: "x", display_name: "X", persona: "new_persona" } }));

    expect(getSession(NOW)?.user.persona).toBe("new_persona");
  });
});
