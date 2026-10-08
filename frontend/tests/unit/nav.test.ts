import { describe, expect, it } from "vitest";

import { isActive } from "@/lib/nav";

describe("isActive", () => {
  it("matches the home link only on the exact root", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/plans", "/")).toBe(false);
  });

  it("matches a section and anything beneath it", () => {
    expect(isActive("/plans", "/plans")).toBe(true);
    expect(isActive("/plans/abc", "/plans")).toBe(true);
    expect(isActive("/plans/", "/plans")).toBe(true);
  });

  it("does not match a different route that merely shares a prefix", () => {
    expect(isActive("/plans-old", "/plans")).toBe(false);
    expect(isActive("/planning", "/plan")).toBe(false);
  });
});
