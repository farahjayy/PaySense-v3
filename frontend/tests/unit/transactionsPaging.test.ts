import { describe, expect, it, vi } from "vitest";

import { fetchAllTransactions } from "@/lib/api/queries";

const get = vi.fn();
vi.mock("@/lib/api/client", () => ({ api: { GET: (...a: unknown[]) => get(...a) } }));

const row = (id: string) => ({ id, date: "2026-01-05", amount_sen: 100 });

describe("fetchAllTransactions", () => {
  it("follows the cursor until the server says there is no next page", async () => {
    get
      .mockResolvedValueOnce({ data: { transactions: [row("a"), row("b")], next_cursor: "c1" } })
      .mockResolvedValueOnce({ data: { transactions: [row("c")], next_cursor: null } });

    const rows = await fetchAllTransactions({ start: "2026-01-01", end: "2026-01-31" });

    expect(rows.map((r) => r.id)).toEqual(["a", "b", "c"]);
    expect(get.mock.calls[0][1].params.query).toEqual({
      start: "2026-01-01",
      end: "2026-01-31",
      cursor: undefined,
    });
    expect(get.mock.calls[1][1].params.query.cursor).toBe("c1");
  });

  it("stops after a bounded number of pages even if the server keeps answering", async () => {
    get.mockReset();
    get.mockResolvedValue({ data: { transactions: [row("x")], next_cursor: "again" } });

    const rows = await fetchAllTransactions({});

    expect(get).toHaveBeenCalledTimes(10);
    expect(rows).toHaveLength(10);
  });
});
