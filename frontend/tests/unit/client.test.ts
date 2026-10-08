import { beforeEach, describe, expect, it, vi } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { getSession, saveSession } from "@/lib/session";

const USER = { id: "u1", username: "amir", display_name: "Amir", persona: null };

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("api client", () => {
  const fetchMock = vi.fn<(request: Request) => Promise<Response>>();

  beforeEach(() => {
    fetchMock.mockReset();
  });

  it("sends the bearer header when a session exists", async () => {
    saveSession({ token: "t-123", expiresAt: Date.now() + 60_000, user: USER });
    fetchMock.mockResolvedValue(jsonResponse(200, USER));
    const api = createApiClient("http://api.test", fetchMock);

    await api.GET("/api/auth/me");

    const request = fetchMock.mock.calls[0][0];
    expect(request.headers.get("authorization")).toBe("Bearer t-123");
    expect(request.url).toBe("http://api.test/api/auth/me");
  });

  it("sends no auth header without a session", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { status: "ok" }));
    const api = createApiClient("http://api.test", fetchMock);

    await api.GET("/api/health");

    expect(fetchMock.mock.calls[0][0].headers.has("authorization")).toBe(false);
  });

  it("forgets the session when the server says it is no longer valid", async () => {
    saveSession({ token: "t-123", expiresAt: Date.now() + 60_000, user: USER });
    fetchMock.mockResolvedValue(
      jsonResponse(401, { detail: { code: "invalid_token", message: "expired" } }),
    );
    const api = createApiClient("http://api.test", fetchMock);

    const { error } = await api.GET("/api/auth/me");

    expect(getSession()).toBeNull();
    expect(error?.detail.code).toBe("invalid_token");
  });

  it("keeps the session when a login attempt itself is rejected", async () => {
    saveSession({ token: "t-123", expiresAt: Date.now() + 60_000, user: USER });
    fetchMock.mockResolvedValue(
      jsonResponse(401, { detail: { code: "unknown_username", message: "nope" } }),
    );
    const api = createApiClient("http://api.test", fetchMock);

    await api.POST("/api/auth/login", { body: { username: "ghost" } });

    expect(getSession()).not.toBeNull();
  });
});
