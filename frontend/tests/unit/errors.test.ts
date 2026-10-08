import { describe, expect, it } from "vitest";

import { errorMessage, NETWORK_ERROR_MESSAGE } from "@/lib/api/errors";

describe("errorMessage", () => {
  it("reads the message out of the API error envelope", () => {
    const body = { detail: { code: "unknown_username", message: "No account with that username." } };

    expect(errorMessage(body)).toBe("No account with that username.");
  });

  it("describes a network failure for a thrown TypeError", () => {
    expect(errorMessage(new TypeError("Failed to fetch"))).toBe(NETWORK_ERROR_MESSAGE);
  });

  it("only treats fetch-style failures as network errors, not any TypeError from a bug", () => {
    expect(errorMessage(new TypeError("Failed to fetch"))).toBe(NETWORK_ERROR_MESSAGE);
    expect(errorMessage(new TypeError("fetch failed"))).toBe(NETWORK_ERROR_MESSAGE);
    expect(errorMessage(new TypeError("NetworkError when attempting to fetch resource."))).toBe(
      NETWORK_ERROR_MESSAGE,
    );
    expect(errorMessage(new TypeError("Cannot read properties of undefined"))).toMatch(
      /something went wrong/i,
    );
  });

  it("falls back for anything it does not recognise", () => {
    expect(errorMessage(undefined)).toMatch(/something went wrong/i);
    expect(errorMessage({ detail: "plain string" })).toMatch(/something went wrong/i);
    expect(errorMessage("boom", "custom fallback")).toBe("custom fallback");
  });
});
