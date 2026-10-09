import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { ApiError, unwrap, useCreateTransaction } from "@/lib/api/queries";
import { NETWORK_ERROR_MESSAGE } from "@/lib/api/errors";

const post = vi.fn();
vi.mock("@/lib/api/client", () => ({ api: { POST: (...a: unknown[]) => post(...a) } }));

describe("unwrap", () => {
  it("returns the data of a successful call", async () => {
    const response = { ok: true, status: 200 } as Response;
    await expect(unwrap(Promise.resolve({ data: { a: 1 }, response }))).resolves.toEqual({ a: 1 });
  });

  it("turns an error response into an ApiError with the server's sentence and code", async () => {
    const response = { ok: false, status: 409 } as Response;
    const error = { detail: { code: "managed_by_plan", message: "Change the plan instead." } };
    const failure = (await unwrap(Promise.resolve({ error, response })).catch(
      (e) => e,
    )) as ApiError;
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({
      message: "Change the plan instead.",
      status: 409,
      code: "managed_by_plan",
    });
  });

  it("turns a request that never reached the server into a readable ApiError, not a raw TypeError", async () => {
    const failure = (await unwrap(Promise.reject(new TypeError("Failed to fetch"))).catch(
      (e) => e,
    )) as ApiError;
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure.message).toBe(NETWORK_ERROR_MESSAGE);
    expect(failure.code).toBe("network_error");
  });
});

describe("ledger mutations", () => {
  it("refresh the provider limits too, since limits are derived from plans", async () => {
    post.mockResolvedValue({ data: { id: "t1" }, response: { ok: true, status: 201 } });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useCreateTransaction(), { wrapper });

    result.current.mutate({
      date: "2026-10-01",
      amount_sen: 100,
      type: "expense",
      category: "Food",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const keys = invalidate.mock.calls.map((c) => (c[0]?.queryKey as string[])[0]);
    expect(keys).toEqual(expect.arrayContaining(["forecast", "plans", "limits", "transactions"]));
  });
});
