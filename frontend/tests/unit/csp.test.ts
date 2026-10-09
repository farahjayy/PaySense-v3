import { describe, expect, it } from "vitest";

import { apiOrigin, buildCsp, newNonce } from "@/lib/csp";

const API = "https://api.example.com";

function directive(policy: string, name: string): string {
  const found = policy.split("; ").find((d) => d.startsWith(`${name} `) || d === name);
  if (!found) throw new Error(`no ${name} directive in: ${policy}`);
  return found;
}

describe("buildCsp", () => {
  const prod = buildCsp({ nonce: "abc123", apiOrigin: API, isDev: false });

  it("allows scripts only by nonce in production: no unsafe-inline, no unsafe-eval", () => {
    const script = directive(prod, "script-src");
    expect(script).toContain("'nonce-abc123'");
    expect(script).toContain("'strict-dynamic'");
    expect(script).not.toContain("unsafe-inline");
    expect(script).not.toContain("unsafe-eval");
  });

  it("limits network destinations to this origin and the API", () => {
    expect(directive(prod, "connect-src")).toBe(`connect-src 'self' ${API}`);
    expect(directive(prod, "default-src")).toBe("default-src 'self'");
  });

  it("blocks framing, plugins, base-tag injection and foreign form posts", () => {
    expect(directive(prod, "frame-ancestors")).toBe("frame-ancestors 'none'");
    expect(directive(prod, "object-src")).toBe("object-src 'none'");
    expect(directive(prod, "base-uri")).toBe("base-uri 'self'");
    expect(directive(prod, "form-action")).toBe("form-action 'self'");
  });

  it("upgrades insecure requests in production only, and permits eval only in development", () => {
    const dev = buildCsp({ nonce: "abc123", apiOrigin: API, isDev: true });
    expect(prod).toContain("upgrade-insecure-requests");
    expect(dev).not.toContain("upgrade-insecure-requests");
    expect(directive(dev, "script-src")).toContain("'unsafe-eval'");
  });
});

describe("newNonce", () => {
  it("is different every time and decodes to a uuid-length value", () => {
    const seen = new Set(Array.from({ length: 50 }, newNonce));
    expect(seen.size).toBe(50);
    expect(Buffer.from([...seen][0], "base64").toString()).toHaveLength(36);
  });
});

describe("apiOrigin", () => {
  it("reduces the configured URL to its origin", () => {
    expect(apiOrigin("https://api.example.com/some/path/", false)).toBe(API);
    expect(apiOrigin("http://localhost:8000", false)).toBe("http://localhost:8000");
  });

  it("falls back to localhost in development but refuses to guess in production", () => {
    expect(apiOrigin(undefined, true)).toBe("http://localhost:8000");
    expect(() => apiOrigin("  ", false)).toThrow(/NEXT_PUBLIC_API_BASE_URL/);
  });

  it("rejects a value that is not a URL", () => {
    expect(() => apiOrigin("not a url", false)).toThrow();
  });
});
