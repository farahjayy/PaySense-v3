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
