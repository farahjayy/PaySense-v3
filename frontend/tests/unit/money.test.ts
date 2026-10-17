import { describe, expect, it } from "vitest";

import { formatAxisRm, formatRm, parseRm } from "@/lib/money";

// These cases mirror backend/tests/domain/test_money.py so the two sides agree on every amount.
describe("parseRm", () => {
  it.each([
    ["0", 0],
    ["12", 1200],
    ["12.5", 1250],
    ["12.50", 1250],
    ["0.05", 5],
    ["1,234.56", 123456],
    ["1,234", 123400],
    ["RM 12", 1200],
    ["rm12.30", 1230],
    ["  RM1,000.00  ", 100000],
  ])("reads %s as %i sen", (text, sen) => {
    expect(parseRm(text)).toBe(sen);
  });

  it.each([
    "",
    "   ",
    "abc",
    "-5",
    "(12.00)",
    "12.345",
    "12.340",
    "1,23",
    "1,2345",
    ".5",
    "12.",
    "1 000",
  ])("rejects %j rather than guessing", (text) => {
    expect(parseRm(text)).toBeNull();
  });

  it("never goes through a float", () => {
    // 0.1 + 0.2 style traps: not exactly representable as binary floats.
    expect(parseRm("0.29")).toBe(29);
    expect(parseRm("1.15")).toBe(115);
    expect(parseRm("4.35")).toBe(435);
    expect(parseRm("19.99")).toBe(1999);
  });

  it("rejects amounts too large to hold exactly", () => {
    expect(parseRm("99,999,999,999,999,999.99")).toBeNull();
  });
});

describe("formatRm", () => {
  it.each([
    [0, "RM 0.00"],
    [5, "RM 0.05"],
    [1250, "RM 12.50"],
    [123456, "RM 1,234.56"],
    [100000000, "RM 1,000,000.00"],
    [-250, "-RM 2.50"],
  ])("formats %i sen as %s", (sen, text) => {
    expect(formatRm(sen)).toBe(text);
  });

  it.each([12.5, Number.NaN, Number.POSITIVE_INFINITY, 2 ** 53])(
    "refuses %s: money is a whole, safe number of sen",
    (sen) => {
      expect(() => formatRm(sen)).toThrow(RangeError);
    },
  );

  it.each([0, 1, 99, 100, 123456, 987654321])("round-trips %i sen through parseRm", (sen) => {
    expect(parseRm(formatRm(sen))).toBe(sen);
  });
});

describe("formatAxisRm", () => {
  it("writes short chart-axis labels that never break across lines", () => {
    expect(formatAxisRm(65000)).toBe("RM 650");
    expect(formatAxisRm(-65000)).toBe("-RM 650");
    expect(formatAxisRm(130000)).toBe("RM 1.3k");
    expect(formatAxisRm(-190000)).toBe("-RM 1.9k");
    expect(formatAxisRm(200000)).toBe("RM 2k");
    expect(formatAxisRm(0)).toBe("RM 0");
  });
});
